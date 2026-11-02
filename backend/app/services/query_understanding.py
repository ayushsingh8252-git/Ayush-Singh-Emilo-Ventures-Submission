"""Query understanding: optional LLM layer in front of the rule-based service.

    user text ──► [LLM → StructuredQuery → validate] ──► OccasionIntent ──► existing engine
              └─► rule-based OccasionService (always computed; used on fallback)

The LLM only affects *how the request is interpreted* (occasion, recipient,
budget, themes). Retrieval, scoring, filtering and every product fact still
come from the existing engine and the catalog.
"""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

from app.services.llm.providers import LLMError, LLMProvider
from app.services.llm.query_parser import (
    StructuredQuery,
    parse_query,
    query_mentions_amount,
    query_mentions_lower_bound,
)
from app.services.occasion_service import CONCEPTS, OccasionIntent, OccasionService, normalize_phrase

logger = logging.getLogger(__name__)

# Circuit breaker: after this many consecutive LLM failures, skip the LLM for
# CIRCUIT_COOLDOWN_SECONDS so users are not each made to wait for a timeout
# during a provider outage. The first success closes the circuit again.
CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_COOLDOWN_SECONDS = 60.0
RECIPIENT_THEME_SCALE = 0.8  # concepts borrowed from a recipient cue count a little less
LLM_THEME_WEIGHT = 0.8  # weight of a theme the LLM selected explicitly
CACHE_SIZE = 256

# Rule-based recipient extraction (also used for evaluation of the rules mode).
_RECIPIENTS = {
    "girlfriend": "girlfriend", "boyfriend": "boyfriend", "wife": "wife", "husband": "husband",
    "fiance": "fiance", "fiancee": "fiancee", "partner": "partner", "spouse": "spouse",
    "mom": "mother", "mum": "mother", "mother": "mother", "mummy": "mother", "maa": "mother",
    "dad": "father", "father": "father", "papa": "father", "daddy": "father",
    "son": "son", "daughter": "daughter", "child": "child", "kid": "child", "kids": "child",
    "toddler": "child", "baby": "baby", "nephew": "nephew", "niece": "niece",
    "brother": "brother", "sister": "sister", "grandma": "grandmother", "grandmother": "grandmother",
    "grandpa": "grandfather", "grandfather": "grandfather", "friend": "friend", "bestie": "friend",
    "colleague": "colleague", "coworker": "colleague", "boss": "boss", "manager": "boss",
    "employee": "employee", "employees": "employee", "team": "team", "client": "client",
    "teacher": "teacher", "mentor": "mentor", "neighbour": "neighbour", "neighbor": "neighbour",
}


def extract_recipient_rules(text: str) -> Optional[str]:
    for word in normalize_phrase(text).split():
        if word in _RECIPIENTS:
            return _RECIPIENTS[word]
    return None


@dataclass
class UnderstandingResult:
    intent: OccasionIntent
    mode: str  # "llm" or "rules"
    recipient: Optional[str] = None
    preferences: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)  # concept phrases
    llm_occasion: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    fallback_reason: Optional[str] = None
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False
    route: str = "rules"  # rules | llm | rules_exact_match (LLM skipped: rules were certain)


class QueryUnderstandingService:
    def __init__(self, occasions: OccasionService, provider: Optional[LLMProvider] = None,
                 status: str = "disabled", status_reason: Optional[str] = None) -> None:
        self.occasions = occasions
        self.provider = provider
        self.status = status
        self.status_reason = status_reason
        self._cache: OrderedDict[str, StructuredQuery] = OrderedDict()
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self.clock = time.monotonic  # injectable for tests

    @property
    def llm_available(self) -> bool:
        return self.provider is not None

    # ------------------------------------------------------------- public
    def understand(self, text: str, use_llm: Optional[bool] = None) -> UnderstandingResult:
        started = time.perf_counter()
        rules = self.occasions.understand(text)
        want_llm = self.llm_available if use_llm is None else use_llm

        if not want_llm:
            return self._rules_result(rules, text, started, fallback=None)
        if not self.llm_available:
            return self._rules_result(rules, text, started, fallback=self.status)
        # Routing: a query that IS a known occasion name ("Diwali", "fathers day") is
        # resolved with certainty by the rules; the LLM would add latency, cost and
        # noise but no information. An explicit use_llm=True still forces the LLM.
        if use_llm is None and rules.match_type == "exact":
            result = self._rules_result(rules, text, started, fallback=None)
            result.route = "rules_exact_match"
            return result

        key = normalize_phrase(text)
        cached = key in self._cache
        if not cached and self.clock() < self._circuit_open_until:
            return self._rules_result(rules, text, started, fallback="circuit_open")
        input_tokens = output_tokens = 0
        try:
            if cached:
                structured = self._cache[key]
                self._cache.move_to_end(key)
            else:
                structured, llm_result = parse_query(self.provider, text)
                input_tokens, output_tokens = llm_result.input_tokens, llm_result.output_tokens
                self._remember(key, structured)
                self._consecutive_failures = 0
        except LLMError as exc:
            self._consecutive_failures += 1
            if self._consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
                self._circuit_open_until = self.clock() + CIRCUIT_COOLDOWN_SECONDS
                logger.warning("LLM failed %d times in a row; skipping it for %.0fs.",
                               self._consecutive_failures, CIRCUIT_COOLDOWN_SECONDS)
            logger.warning("LLM query understanding failed (%s); using rules.", exc.kind)
            return self._rules_result(rules, text, started, fallback=exc.kind)

        intent = self._intent_from_structured(structured, rules, text)
        return UnderstandingResult(
            intent=intent,
            mode="llm",
            recipient=structured.recipient,
            preferences=structured.preferences,
            themes=[CONCEPTS[k].phrase for k in structured.themes],
            llm_occasion=structured.occasion,
            provider=self.provider.name,
            model=self.provider.model,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached=cached,
            route="llm",
        )

    # ------------------------------------------------------------ helpers
    def _remember(self, key: str, structured: StructuredQuery) -> None:
        self._cache[key] = structured
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

    def _rules_result(self, rules: OccasionIntent, text: str, started: float,
                      fallback: Optional[str]) -> UnderstandingResult:
        return UnderstandingResult(
            intent=rules,
            mode="rules",
            recipient=extract_recipient_rules(text),
            themes=[c.phrase for c in rules.concepts],
            fallback_reason=fallback,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def _intent_from_structured(self, sq: StructuredQuery, rules: OccasionIntent, text: str) -> OccasionIntent:
        """Translate validated LLM output into the engine's existing intent type."""
        profiles, display_override = [], None
        if sq.occasion:
            occ = self.occasions.understand(sq.occasion)
            if occ.matched_profiles and occ.match_type in {"exact", "phrase", "fuzzy", "semantic"}:
                profiles = [p for p in occ.matched_profiles if p.is_occasion] or occ.matched_profiles
            else:
                display_override = sq.occasion  # an occasion outside the library, e.g. "Promotion"
        if profiles:
            # Headline = the occasion only; recipient cues below add themes, not a title.
            display_override = " + ".join(p.name for p in profiles)
        elif not display_override:
            profiles = list(rules.matched_profiles)  # LLM found no occasion: keep what rules found
            display_override = rules.display_name or (sq.recipient.title() if sq.recipient else None)

        weights: dict[str, float] = {}
        for profile in profiles:
            for key, weight in profile.concepts.items():
                weights[key] = max(weights.get(key, 0.0), weight)

        recipient_profiles = self.occasions.match_aliases(sq.recipient) if sq.recipient else []
        for profile in recipient_profiles:
            if profile in profiles:
                continue
            for key, weight in profile.concepts.items():
                weights[key] = max(weights.get(key, 0.0), weight * RECIPIENT_THEME_SCALE)

        for key in sq.themes:
            weights[key] = max(weights.get(key, 0.0), LLM_THEME_WEIGHT)

        # Budget: an explicit amount parsed by the deterministic rules wins. An LLM
        # budget is accepted only if the shopper's words contain an amount, and an
        # LLM *minimum* only if they asked for one ("around 1000" must not hide a
        # perfect ₹719 match behind an invented lower bound).
        min_price, max_price = rules.min_price, rules.max_price
        if min_price is None and max_price is None and query_mentions_amount(text):
            max_price = sq.max_price
            min_price = sq.min_price if query_mentions_lower_bound(text) else None

        extra = " ".join(
            filter(None, [
                f"Gift for {sq.recipient}." if sq.recipient else "",
                f"Occasion: {display_override}." if display_override else "",
                ("Themes: " + ", ".join(CONCEPTS[k].phrase for k in sq.themes) + ".") if sq.themes else "",
                ("Preferences: " + ", ".join(sq.preferences) + ".") if sq.preferences else "",
            ])
        )
        has_signal = bool(profiles or display_override or weights or rules.keyword_terms)
        return OccasionIntent(
            raw_query=text,
            search_text=rules.search_text,
            keyword_terms=rules.keyword_terms,  # keyword relevance stays tied to the user's own words
            concept_weights=weights,
            matched_profiles=profiles + [p for p in recipient_profiles if p not in profiles],
            match_type="llm" if has_signal else "generic",
            min_price=min_price,
            max_price=max_price,
            display_override=display_override,
            extra_expansion=extra,
        )
