"""Pure scoring functions. Every component returns a value in [0, 1]."""

from __future__ import annotations

import math
from typing import Iterable, Mapping

from app.config import ScoringWeights


def calibrate_similarity(cosine: float, floor: float, ceil: float) -> float:
    """Map a raw cosine similarity linearly onto [0, 1].

    A fixed (not per-query min-max) calibration keeps scores comparable across
    queries, which is what makes an absolute relevance threshold possible.
    """
    if ceil <= floor:
        return max(0.0, min(1.0, cosine))
    return max(0.0, min(1.0, (cosine - floor) / (ceil - floor)))


def compute_idf(doc_token_sets: Iterable[frozenset[str]]) -> dict[str, float]:
    """Smoothed IDF over product documents."""
    sets = list(doc_token_sets)
    n = len(sets)
    df: dict[str, int] = {}
    for tokens in sets:
        for token in tokens:
            df[token] = df.get(token, 0) + 1
    return {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}


# A "field" is (token set, weight). Product documents expose title, body and
# boilerplate fields, weighted from most to least product-specific.
Field = tuple[frozenset[str], float]


def keyword_relevance(terms: list[str], fields: list[Field], idf: Mapping[str, float]) -> tuple[float, list[str]]:
    """IDF-weighted fraction of query terms found in the product.

    Each term counts with the weight of the strongest field containing it.
    Terms absent from the whole catalog carry no information and are excluded
    from the denominator. Returns (score, matched_terms).
    """
    known = [t for t in terms if t in idf]
    total = sum(idf[t] for t in known)
    if total == 0:
        return 0.0, []
    score, matched = 0.0, []
    for term in known:
        weight = max((w for tokens, w in fields if term in tokens), default=0.0)
        if weight > 0:
            score += idf[term] * weight
            matched.append(term)
    return min(1.0, score / total), matched


def concept_relevance(concept_weights: Mapping[str, float], concept_keywords: Mapping[str, tuple[str, ...]],
                      fields: list[Field]) -> tuple[float, dict[str, list[str]]]:
    """Noisy-OR over the occasion's concepts that the product expresses.

    A concept's strength is its occasion weight times the weight of the
    strongest field mentioning it (title > description > boilerplate).
    Noisy-OR keeps the result in [0, 1] while rewarding products that hit
    several concepts. Returns (score, {concept_key: matched_terms}).
    """
    miss_probability = 1.0
    matched: dict[str, list[str]] = {}
    for key, weight in concept_weights.items():
        hits, field_weight = [], 0.0
        for tokens, w in fields:
            found = [k for k in concept_keywords[key] if k in tokens]
            if found:
                hits.extend(found)
                field_weight = max(field_weight, w)
        if not hits:
            continue
        miss_probability *= 1.0 - min(weight * field_weight, 1.0)
        matched[key] = list(dict.fromkeys(hits))
    return 1.0 - miss_probability, matched


def combine_scores(semantic: float, keyword: float, concept: float, weights: ScoringWeights,
                   keyword_informative: bool, concept_informative: bool) -> float:
    """Weighted sum, re-normalising weights over the informative components.

    If no product matches any query term (e.g. "Valentine's Day" - no listing
    contains the word "valentine"), the keyword component is zero for every
    product. Keeping its weight would only cap all scores at 0.75 and make the
    relevance threshold query-dependent, so its weight is redistributed.
    """
    parts = [(weights.semantic, semantic)]
    if keyword_informative:
        parts.append((weights.keyword, keyword))
    if concept_informative:
        parts.append((weights.concept, concept))
    total_weight = sum(w for w, _ in parts)
    return sum(w * v for w, v in parts) / total_weight if total_weight else 0.0
