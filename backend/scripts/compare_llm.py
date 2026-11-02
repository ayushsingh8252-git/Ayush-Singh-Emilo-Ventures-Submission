"""Compare rule-based vs LLM-enhanced query understanding on the real catalog.

Usage (from ./backend, needs GEMINI_API_KEY; makes real, billable API calls):
    python -m scripts.compare_llm                # writes ../docs/llm_evaluation.md and .json

Measures, for each mode:
  * recommendation relevance  - nDCG@10 / P@10 against hand-written judgments; products outside
                                the query's stated budget get gain 0
  * query understanding       - occasion, recipient and budget accuracy against expected labels
  * response latency          - end-to-end recommend() time (LLM calls are cold: cache cleared)
  * API cost                  - tokens reported by Gemini x configured list prices
  * fallback reliability      - injected failures + a real network timeout must reproduce the
                                rule-based results exactly
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("LLM_ENABLED", "true")

from app.config import settings  # noqa: E402
from app.models.product import RecommendRequest  # noqa: E402
from app.services.llm.providers import GeminiProvider, LLMError, LLMResult, create_provider  # noqa: E402
from app.services.query_understanding import QueryUnderstandingService  # noqa: E402
from app.services.recommendation_service import RecommendationEngine  # noqa: E402
from scripts.relevance_judgments import grade  # noqa: E402

K = 10
# Seconds to wait before each live LLM call (outside the timed section), so the
# provider's requests-per-minute limit does not turn into measured failures.
PACE_SECONDS = float(os.getenv("COMPARE_PACE_SECONDS", "5"))
OUT_DIR = Path(__file__).resolve().parents[2] / "docs"

# expected: accepted occasion labels (None = no occasion stated), recipient, budget (min, max) or None.
# judge: which judgment set grades the results.
CASES = [
    # --- plain occasion names (what v1 was built for) ---------------------------------
    *[dict(q=o, occ={o}, rec=None, budget=None, judge=o) for o in (
        "Birthday", "Wedding", "Valentine's Day", "Diwali", "Anniversary", "Office Party",
        "Father's Day", "Mother's Day", "Baby Shower", "Graduation", "Housewarming")],
    # --- natural-language requests ------------------------------------------------------
    dict(q="Suggest a romantic gift for my girlfriend under ₹2,000.", occ={"Valentine's Day", "Romantic", None},
         rec="girlfriend", budget=(None, 2000), judge="Valentine's Day"),
    dict(q="somthing for my mom's bday, nothing above 1500 rupees", occ={"Birthday"},
         rec="mother", budget=(None, 1500), judge="Mother's Day"),
    dict(q="my colleague is retiring next week, he loves watches", occ={"Retirement"},
         rec="colleague", budget=None, judge="Retirement"),
    dict(q="need a diwali present for my team, budget 1k each", occ={"Diwali"},
         rec="team", budget=(None, 1000), judge="Diwali"),
    dict(q="anniversery gift for my wife, something personal", occ={"Anniversary"},
         rec="wife", budget=None, judge="Anniversary"),
    dict(q="my 6 year old nephew's birthday", occ={"Birthday"},
         rec="nephew", budget=None, judge="Kids"),
    dict(q="housewarming for a friend who loves plants, around 1000", occ={"Housewarming"},
         rec="friend", budget="around 1000", judge="Housewarming"),
    dict(q="thank you gift for my teacher", occ={"Teacher's Day", "Thank You"},
         rec="teacher", budget=None, judge="Teacher"),
    dict(q="eco friendly gift for my sister who is into yoga", occ={None, "Eco-conscious"},
         rec="sister", budget=None, judge="Eco Wellness"),
    dict(q="farewell gift for my boss under 3000", occ={"Office Party", "Farewell", "Retirement"},
         rec="boss", budget=(None, 3000), judge="Office Party"),
    dict(q="baby shower present for my cousin, something cute", occ={"Baby Shower"},
         rec="cousin", budget=None, judge="Baby Shower"),
    dict(q="valentines gift for husband", occ={"Valentine's Day"},
         rec="husband", budget=None, judge="Valentine's Day"),
    dict(q="something for dad who likes writing, below 1000", occ={None, "Father's Day"},
         rec="father", budget=(None, 1000), judge="Father's Day"),
    dict(q="gift for a 10 yr old who loves music", occ={None, "Birthday", "Kids"},
         rec="child", budget=None, judge="Kids"),
    dict(q="christmas hamper for clients between 1500 and 3000", occ={"Christmas"},
         rec="client", budget=(1500, 3000), judge="Christmas"),
]
RECIPIENT_SYNONYMS = {"mom": "mother", "mum": "mother", "dad": "father", "clients": "client",
                      "kid": "child", "boy": "child", "girl": "child", "team members": "team", "employees": "team"}


def dcg(gains):
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains[:K]))


def in_budget(price, budget) -> bool:
    if budget is None or price is None:
        return True
    if budget == "around 1000":  # same definition as budget_correct(): at most ~₹1,500
        return price <= 1500
    lo, hi = budget
    return (lo is None or price >= lo) and (hi is None or price <= hi)


def budget_correct(case, it) -> bool:
    lo, hi = it.applied_min_price, it.applied_max_price
    expected = case["budget"]
    if expected is None:
        return lo is None and hi is None
    if expected == "around 1000":  # any sensible range around ₹1,000 counts
        return hi is not None and 1000 <= hi <= 1500 and (lo is None or lo <= 1000)
    return (lo or None) == expected[0] and hi == expected[1]


def recipient_correct(case, it) -> bool:
    got = (it.recipient or "").strip().lower()
    got = RECIPIENT_SYNONYMS.get(got, got)
    return got == (case["rec"] or "")


def evaluate(engine, titles, use_llm):
    """use_llm: False = rules only, True = LLM on every query, None = shipped routing."""
    rows = []
    for case in CASES:
        if use_llm is not False:
            engine.understanding._cache.clear()  # measure cold LLM calls
            if use_llm or engine.understanding.occasions.understand(case["q"]).match_type != "exact":
                time.sleep(PACE_SECONDS)
        started = time.perf_counter()
        res = engine.recommend(RecommendRequest(query=case["q"], limit=K, use_llm=use_llm))
        latency = (time.perf_counter() - started) * 1000
        it = res.interpretation
        gains = [grade(case["judge"], r.name) if in_budget(r.final_price, case["budget"]) else 0
                 for r in res.recommendations]
        ideal = sorted((grade(case["judge"], t) for t, p in titles if in_budget(p, case["budget"])), reverse=True)
        rows.append(dict(
            query=case["q"], kind="occasion" if case["q"] in {c["q"] for c in CASES[:11]} else "natural language",
            mode=it.understanding_mode, route=it.understanding_route, fallback=it.llm_fallback_reason,
            occasion=it.matched_occasion, recipient=it.recipient,
            budget=[it.applied_min_price, it.applied_max_price], preferences=it.preferences,
            ndcg=dcg(gains) / dcg(ideal) if dcg(ideal) else 0.0,
            p10=sum(g > 0 for g in gains) / len(gains) if gains else 0.0,
            results=len(gains),
            occ_ok=it.matched_occasion in case["occ"], rec_ok=recipient_correct(case, it),
            budget_ok=budget_correct(case, it),
            latency_ms=latency, understanding_ms=it.understanding_latency_ms,
            top3=[r.name for r in res.recommendations[:3]],
        ))
    return rows


class FailingProvider:
    name, model = "failing", "none"

    def __init__(self, kind):
        self.kind = kind

    def generate_json(self, *_):
        raise LLMError(self.kind)


class GarbageProvider:
    name, model = "garbage", "none"

    def generate_json(self, *_):
        return LLMResult(data={"occasion": 123, "max_price": "a lot"}, model="none", latency_ms=1)


def fallback_reliability(engine, real_provider):
    """Every failure mode must return exactly the rule-based result list."""
    original = engine.understanding
    scenarios = {kind: FailingProvider(kind) for kind in ("timeout", "http_error", "network", "invalid_response")}
    scenarios["malformed JSON fields"] = GarbageProvider()
    if real_provider is not None:  # a REAL network timeout against the live endpoint
        scenarios["real 1 ms timeout"] = GeminiProvider(settings.gemini_api_key, settings.gemini_model,
                                                        timeout_seconds=0.001)
    baseline = {c["q"]: [r.product_id for r in engine.recommend(
        RecommendRequest(query=c["q"], limit=K, use_llm=False)).recommendations] for c in CASES}
    report = {}
    for name, provider in scenarios.items():
        engine.understanding = QueryUnderstandingService(engine.occasions, provider, "ready")
        identical = errors = 0
        reasons = set()
        for case in CASES:
            try:
                res = engine.recommend(RecommendRequest(query=case["q"], limit=K))
                reasons.add(res.interpretation.llm_fallback_reason)
                identical += [r.product_id for r in res.recommendations] == baseline[case["q"]]
            except Exception:  # noqa: BLE001 - counted, never expected
                errors += 1
        report[name] = dict(identical=identical, total=len(CASES), errors=errors, reasons=sorted(map(str, reasons)))
    # missing key: no provider at all
    engine.understanding = QueryUnderstandingService(engine.occasions, None, "missing_key")
    same = sum([r.product_id for r in engine.recommend(RecommendRequest(query=c["q"], limit=K, use_llm=True))
                .recommendations] == baseline[c["q"]] for c in CASES)
    report["missing API key"] = dict(identical=same, total=len(CASES), errors=0, reasons=["missing_key"])
    engine.understanding = original
    return report


def summarize(rows, kind=None):
    rows = [r for r in rows if kind is None or r["kind"] == kind]
    pct = lambda key: 100 * sum(r[key] for r in rows) / len(rows)  # noqa: E731
    lat = sorted(r["latency_ms"] for r in rows)
    return dict(
        n=len(rows), ndcg=statistics.mean(r["ndcg"] for r in rows), p10=statistics.mean(r["p10"] for r in rows),
        occ=pct("occ_ok"), rec=pct("rec_ok"), budget=pct("budget_ok"),
        lat_p50=statistics.median(lat), lat_p95=lat[max(0, math.ceil(0.95 * len(lat)) - 1)],
        lat_mean=statistics.mean(lat),
    )


def main() -> int:
    logging.basicConfig(level=logging.ERROR)
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = dataclasses.replace(settings, llm_enabled=True)
    provider, status, reason = create_provider(cfg)
    if provider is None:
        print(f"LLM unavailable ({status}: {reason}); set LLM_ENABLED=true and GEMINI_API_KEY.")
        return 1

    # Wrap the provider to record token usage of every real call.
    usage = []
    real_generate = provider.generate_json

    def counting(system, user, schema):
        result = real_generate(system, user, schema)
        usage.append((result.input_tokens, result.output_tokens, result.latency_ms))
        return result

    provider.generate_json = counting
    engine = RecommendationEngine.build(cfg)
    engine.understanding = QueryUnderstandingService(engine.occasions, provider, status)
    titles = [(d.product.title, d.product.final_price) for d in engine.docs]

    engine.recommend(RecommendRequest(query="warm-up", use_llm=False))  # load/JIT outside timings
    rules = evaluate(engine, titles, use_llm=False)
    llm = evaluate(engine, titles, use_llm=True)
    always_usage = list(usage)
    routed = evaluate(engine, titles, use_llm=None)
    routed_usage = usage[len(always_usage):]
    fallback = fallback_reliability(engine, provider)

    def cost_of(records):
        t_in, t_out = sum(u[0] for u in records), sum(u[1] for u in records)
        usd = t_in / 1e6 * cfg.llm_input_price_per_m + t_out / 1e6 * cfg.llm_output_price_per_m
        return dict(calls=len(records), tokens_in=t_in, tokens_out=t_out, usd=usd,
                    usd_per_1000_queries=usd / len(CASES) * 1000)

    tokens_in = sum(u[0] for u in usage)
    tokens_out = sum(u[1] for u in usage)
    calls = len(usage)
    cost = tokens_in / 1e6 * cfg.llm_input_price_per_m + tokens_out / 1e6 * cfg.llm_output_price_per_m
    llm_failures = sum(r["fallback"] is not None for r in llm + routed)

    result = dict(
        model=f"{provider.name}/{provider.model}", cases=len(CASES),
        summary={m: {k: summarize(rows, k) for k in (None, "occasion", "natural language")}
                 for m, rows in (("rules", rules), ("llm", llm), ("routed", routed))},
        mode_cost=dict(llm=cost_of(always_usage), routed=cost_of(routed_usage)),
        cost=dict(calls=calls, tokens_in=tokens_in, tokens_out=tokens_out, usd=cost,
                  usd_per_1000_queries=cost / calls * 1000 if calls else 0,  # per LLM call
                  price_in=cfg.llm_input_price_per_m, price_out=cfg.llm_output_price_per_m,
                  llm_call_latency_ms_mean=statistics.mean(u[2] for u in usage) if usage else 0),
        llm_live_failures=llm_failures, fallback=fallback, rows=dict(rules=rules, llm=llm, routed=routed),
    )
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "llm_evaluation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str),
                                                 encoding="utf-8")
    (OUT_DIR / "llm_evaluation.md").write_text(render(result), encoding="utf-8")
    print(render(result))
    return 0


def render(r) -> str:
    s = r["summary"]
    lines = [
        "# Rule-based vs LLM-enhanced query understanding",
        "",
        f"Generated by `python -m scripts.compare_llm` on the real catalog with **{r['model']}**. "
        f"{r['cases']} queries: 11 plain occasion names + {r['cases'] - 11} natural-language requests. "
        "Relevance is graded against the author-written judgments in `scripts/relevance_judgments.py` "
        "(not independent ground truth; products outside a query's stated budget get gain 0).",
        "",
        "## Summary",
        "",
        "Three configurations: **Rules** (no LLM), **LLM always** (every query goes to the LLM) and "
        "**Routed** (shipped default: exact occasion names use the rules, everything else the LLM).",
        "",
        "| Metric | Query set | Rules | LLM always | Routed (default) |",
        "|---|---|---|---|---|",
    ]
    modes = ("rules", "llm", "routed")
    for label, key in (("All", None), ("Occasion names", "occasion"), ("Natural language", "natural language")):
        lines.append(f"| nDCG@10 | {label} | " + " | ".join(f"{s[m][key]['ndcg']:.3f}" for m in modes) + " |")
        lines.append(f"| P@10 | {label} | " + " | ".join(f"{s[m][key]['p10']:.2f}" for m in modes) + " |")
    for name, field in (("Occasion understood", "occ"), ("Recipient extracted", "rec"), ("Budget correct", "budget")):
        lines.append(f"| {name} | Natural language | " + " | ".join(
            f"{s[m]['natural language'][field]:.0f}%" for m in modes) + " |")
    for name, field in (("Latency p50 (end-to-end)", "lat_p50"), ("Latency p95 (end-to-end)", "lat_p95")):
        lines.append(f"| {name} | All | " + " | ".join(f"{s[m][None][field]:.0f} ms" for m in modes) + " |")
    mc = r["mode_cost"]
    lines += [
        f"| LLM calls (26 queries) | All | 0 | {mc['llm']['calls']} | {mc['routed']['calls']} |",
        f"| API cost per 1,000 queries | All | $0 | ${mc['llm']['usd_per_1000_queries']:.3f} | "
        f"${mc['routed']['usd_per_1000_queries']:.3f} |",
        "",
        f"Cost basis: {r['cost']['calls']} live calls in total, {r['cost']['tokens_in']:,} input + "
        f"{r['cost']['tokens_out']:,} output tokens (output includes thinking tokens), priced at "
        f"${r['cost']['price_in']}/1M input and ${r['cost']['price_out']}/1M output (paid Standard tier list "
        "price; the free tier costs $0 within its rate limits). Per-1,000 figures assume this query mix; "
        "repeated queries are cached and cost nothing.",
        "",
        f"Live LLM calls that failed and fell back during this run: {r['llm_live_failures']}.",
        "",
        "## Fallback reliability",
        "",
        "Each scenario replays all queries; results must be identical to the rule-based mode.",
        "",
        "| Failure scenario | Identical results | Errors raised | Reported fallback reason |",
        "|---|---|---|---|",
    ]
    for name, f in r["fallback"].items():
        lines.append(f"| {name} | {f['identical']}/{f['total']} | {f['errors']} | {', '.join(f['reasons'])} |")
    lines += ["", "## Per-query results", "",
              "| Query | Mode | Occasion | Recipient | Budget | nDCG@10 | Top 3 |", "|---|---|---|---|---|---|---|"]
    for mode in ("rules", "llm", "routed"):
        for row in r["rows"][mode]:
            b = row["budget"]
            budget = "-" if b == [None, None] else f"{b[0] or ''}–{b[1] or ''}"
            lines.append(f"| {row['query']} | {mode} | {row['occasion'] or '-'} | {row['recipient'] or '-'} | "
                         f"{budget} | {row['ndcg']:.2f} | {', '.join(row['top3'])} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
