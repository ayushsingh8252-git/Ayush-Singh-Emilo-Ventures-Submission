"""Internal product model and API schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Product(BaseModel):
    """Normalised product, independent of the raw catalog's field names."""

    product_id: str
    vendor_id: str = ""
    category_id: str = ""
    category_label: str = "Uncategorised"
    product_group_id: str = ""
    title: str
    slug: str = ""
    description: str = ""
    short_description: str = ""
    brand: str = ""
    sku: str = ""
    image_url: Optional[str] = None
    price: Optional[float] = None
    discount_percentage: float = 0.0
    stock: int = 0
    is_approved: bool = False
    status: str = ""
    deleted_at: Optional[str] = None

    @property
    def final_price(self) -> Optional[float]:
        if self.price is None:
            return None
        return round(self.price * (1 - self.discount_percentage / 100), 2)


class RecommendRequest(BaseModel):
    occasion: str = Field(..., description="Occasion or free-text gifting intent, e.g. 'Diwali'.")
    limit: int = Field(10, ge=1, le=24)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    category: Optional[str] = Field(None, description="Category ID to restrict results to.")

    @field_validator("occasion")
    @classmethod
    def _strip_occasion(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Occasion must not be empty.")
        if len(value) > 200:
            raise ValueError("Occasion must be at most 200 characters.")
        return value

    @field_validator("category")
    @classmethod
    def _blank_category_is_none(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class ScoreBreakdown(BaseModel):
    semantic: float
    keyword: float
    concept: float


class Recommendation(BaseModel):
    product_id: str
    name: str
    description: str
    short_description: str
    brand: str
    category_id: str
    category_label: str
    image_url: Optional[str]
    price: Optional[float]
    final_price: Optional[float]
    discount_percentage: float
    stock: int
    similarity_score: float = Field(..., description="Final hybrid relevance score in [0, 1].")
    score_breakdown: ScoreBreakdown
    matched_concepts: list[str]
    reason: str


class OccasionInterpretation(BaseModel):
    matched_occasion: Optional[str]
    match_type: str
    concepts: list[str]
    applied_max_price: Optional[float] = None
    applied_min_price: Optional[float] = None


class RecommendResponse(BaseModel):
    occasion: str
    interpretation: OccasionInterpretation
    total_results: int
    recommendation_mode: str
    recommendations: list[Recommendation]
    message: Optional[str] = None
