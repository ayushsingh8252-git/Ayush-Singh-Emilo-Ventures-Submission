"""Print ranked recommendations for a set of manual test queries.

Usage (from ./backend):
    python -m scripts.evaluate_queries                 # semantic mode
    python -m scripts.evaluate_queries --fallback      # TF-IDF fallback mode
    python -m scripts.evaluate_queries "Eid" "farewell gift"
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

from app.config import settings
from app.models.product import RecommendRequest
from app.services.recommendation_service import RecommendationEngine

DEFAULT_QUERIES = [
    "Valentine's Day", "Birthday", "Wedding", "Diwali", "Office Party", "Graduation", "Housewarming",
    "Something romantic for my girlfriend", "Gift for a child", "Something under ₹1,000",
    "Christmas", "Mother's Day", "Father's Day", "Baby Shower", "Anniversary",
    "aniversary", "Eid celebration", "retirement", "zzqx",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("queries", nargs="*")
    parser.add_argument("--fallback", action="store_true", help="force the TF-IDF fallback")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--reasons", action="store_true", help="print the explanation for each result")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    sys.stdout.reconfigure(encoding="utf-8")
    engine = RecommendationEngine.build(dataclasses.replace(settings, force_fallback=args.fallback))
    print(f"mode={engine.mode} vector_store={engine.store.backend} indexed={engine.store.size}\n")

    for query in args.queries or DEFAULT_QUERIES:
        result = engine.recommend(RecommendRequest(occasion=query, limit=args.limit))
        it = result.interpretation
        print(f"=== {query!r} -> {it.matched_occasion} [{it.match_type}] "
              f"budget=({it.applied_min_price}, {it.applied_max_price}) results={result.total_results}")
        for rank, rec in enumerate(result.recommendations, 1):
            b = rec.score_breakdown
            print(f"  {rank:2d}. {rec.similarity_score:.3f} (sem {b.semantic:.2f} kw {b.keyword:.2f} "
                  f"con {b.concept:.2f})  {rec.name}  [{rec.category_label}]  ₹{rec.final_price}")
            if args.reasons:
                print(f"        {rec.reason}")
        if result.message:
            print(f"  -> {result.message}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
