"""HTTP routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.models.product import RecommendRequest, RecommendResponse
from app.services.recommendation_service import RecommendationEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

EXAMPLE_QUERIES = [
    "Something romantic for my girlfriend",
    "Gift for a child",
    "Something under ₹1,000",
    "Housewarming gift for a new home",
    "Corporate gift for my team",
]


def get_engine(request: Request) -> RecommendationEngine:
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Recommendation engine is not ready yet.")
    return engine


@router.get("/health")
def health(engine: RecommendationEngine = Depends(get_engine)) -> dict:
    return engine.health()


@router.get("/occasions")
def occasions(engine: RecommendationEngine = Depends(get_engine)) -> dict:
    return {"occasions": engine.occasions.occasion_names, "examples": EXAMPLE_QUERIES}


@router.get("/categories")
def categories(engine: RecommendationEngine = Depends(get_engine)) -> dict:
    """Categories present among eligible products. Labels are inferred from
    product text because the catalog only provides opaque category IDs."""
    return {"categories": engine.categories()}


# A sync handler runs in FastAPI's thread pool, so CPU-bound encoding does not
# block the event loop.
@router.post("/recommend", response_model=RecommendResponse)
def recommend(payload: RecommendRequest, engine: RecommendationEngine = Depends(get_engine)) -> RecommendResponse:
    if payload.min_price is not None and payload.max_price is not None and payload.min_price > payload.max_price:
        raise HTTPException(status_code=422, detail="min_price must not exceed max_price.")
    try:
        return engine.recommend(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Recommendation failed for %r", payload.occasion)
        raise HTTPException(status_code=500, detail="Could not compute recommendations.") from exc
