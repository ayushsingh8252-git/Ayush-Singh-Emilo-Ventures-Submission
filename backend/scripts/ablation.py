"""Compare ranking configurations against the hand-written judgments.

Usage (from ./backend):  python -m scripts.ablation

Metrics per configuration, averaged over the 11 audited occasions:
  nDCG@10     graded (2/1/0) ranking quality, ideal = best possible top-10 from the catalog
  P@10        share of returned items with grade >= 1
  wrong-occ   products titled for a *different* occasion in the top 10 (summed)
  add-ons     wrapping / seals / gift boxes in the top 10 (summed)
"""

from __future__ import annotations

import dataclasses
import logging
import math
import sys

from app.config import ScoringWeights, settings
from app.models.product import RecommendRequest
from app.services import preprocessing
from app.services.recommendation_service import RecommendationEngine
from scripts.relevance_judgments import ADD_ONS, JUDGMENTS, OCCASION_TITLE_WORDS, grade

K = 10


def dcg(gains: list[int]) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains[:K]))


def wrong_occasion(occasion: str, title: str) -> bool:
    lowered = title.lower()
    return any(w in lowered and owner != occasion for w, owner in OCCASION_TITLE_WORDS.items())


def evaluate(engine: RecommendationEngine) -> dict[str, float]:
    titles = [d.product.title for d in engine.docs]
    ndcgs, precisions, wrong, addons, per_occ = [], [], 0, 0, {}
    for occasion in JUDGMENTS:
        recs = engine.recommend(RecommendRequest(occasion=occasion, limit=K)).recommendations
        gains = [grade(occasion, r.name) for r in recs]
        ideal = sorted((grade(occasion, t) for t in titles), reverse=True)
        ndcg = dcg(gains) / dcg(ideal) if dcg(ideal) else 0.0
        ndcgs.append(ndcg)
        precisions.append(sum(g > 0 for g in gains) / len(gains) if gains else 0.0)
        wrong += sum(wrong_occasion(occasion, r.name) for r in recs)
        addons += sum(bool(ADD_ONS.search(r.name)) for r in recs)
        per_occ[occasion] = ndcg
    return {"ndcg": sum(ndcgs) / len(ndcgs), "p10": sum(precisions) / len(precisions),
            "wrong": wrong, "addons": addons, "per_occasion": per_occ}


def main() -> int:
    logging.basicConfig(level=logging.ERROR)
    sys.stdout.reconfigure(encoding="utf-8")
    def cfg(weights=(0.55, 0.20, 0.25), conflict=0.5, add_on=0.7):
        return dataclasses.replace(settings, weights=ScoringWeights(*weights),
                                   occasion_conflict_strength=conflict, accessory_factor=add_on)

    base = cfg()  # the shipped configuration
    configs = {
        "A semantic only (1/0/0)": cfg(weights=(1.0, 0.0, 0.0)),
        "B brief weights 0.65/0.25/0.10": cfg(weights=(0.65, 0.25, 0.10)),
        "C no concepts 0.70/0.30/0": cfg(weights=(0.70, 0.30, 0.0)),
        "D v1.0: conflict 0.3, no add-on rule": cfg(conflict=0.3, add_on=1.0),
        "E shipped, no occasion conflict": cfg(conflict=0.0),
        "F shipped, no add-on rule": cfg(add_on=1.0),
        "H shipped: 0.55/0.20/0.25, 0.5, x0.7": base,
    }
    engine = RecommendationEngine.build(base)  # embeddings computed once, reused below
    results = {}
    for name, cfg in configs.items():
        engine.settings = cfg
        results[name] = evaluate(engine)

    # Boilerplate handling off: rebuild documents with no shared text detected.
    original = preprocessing.find_boilerplate
    preprocessing.find_boilerplate = lambda products: set()
    try:
        results["J shipped, boilerplate handling off"] = evaluate(RecommendationEngine.build(base))
    finally:
        preprocessing.find_boilerplate = original

    print(f"mode={engine.mode}\n")
    print(f"{'configuration':38s} {'nDCG@10':>8s} {'P@10':>6s} {'wrong-occ':>10s} {'add-ons':>8s}")
    for name, r in results.items():
        print(f"{name:38s} {r['ndcg']:8.3f} {r['p10']:6.2f} {r['wrong']:10d} {r['addons']:8d}")
    print("\nper-occasion nDCG@10 (v1.0 D -> shipped H):")
    for occ in JUDGMENTS:
        d, h = results["D v1.0: conflict 0.3, no add-on rule"], results["H shipped: 0.55/0.20/0.25, 0.5, x0.7"]
        print(f"  {occ:16s} {d['per_occasion'][occ]:.3f} -> {h['per_occasion'][occ]:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
