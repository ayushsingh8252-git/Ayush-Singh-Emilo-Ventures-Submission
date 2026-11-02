"""Shared fixtures.

Engines are built once per session: the semantic one uses the real
``all-MiniLM-L6-v2`` model (tests depending on it are skipped if the model
cannot be loaded), the fallback one forces TF-IDF.
"""

from __future__ import annotations

import os

# Tests must never call a real LLM API: force the optional LLM layer off before
# app.config reads the environment (a real env var beats any .env file).
os.environ["LLM_ENABLED"] = "false"

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.services.data_loader import load_catalog
from app.services.embedding_service import MODE_SEMANTIC
from app.services.recommendation_service import RecommendationEngine


def make_record(**overrides) -> dict:
    """A raw catalog record in the real products.json schema (test fixture)."""
    record = {
        "id": "p-1",
        "shopId": "shop-1",
        "categoryId": "cat-1",
        "name": "Test Rose Bouquet",
        "slug": "test-rose-bouquet",
        "description": "A romantic bouquet of red roses.",
        "shortDescription": "Red roses.",
        "mainImage": "https://example.com/rose.png",
        "brand": "Test Brand",
        "sku": "SKU-1",
        "price": "999",
        "discountPercentage": "10",
        "stock": 10,
        "isApproved": True,
        "status": "ACTIVE",
        "deletedAt": None,
        "productGroupId": "group-1",
        "updatedAt": "2026-01-01T00:00:00.000Z",
    }
    record.update(overrides)
    return record


@pytest.fixture(scope="session")
def raw_catalog() -> list[dict]:
    with settings.data_path.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def catalog():
    return load_catalog(settings.data_path)


@pytest.fixture(scope="session")
def semantic_engine() -> RecommendationEngine:
    engine = RecommendationEngine.build(settings)
    if engine.mode != MODE_SEMANTIC:
        pytest.skip(f"Embedding model unavailable: {engine.fallback_reason}")
    return engine


@pytest.fixture(scope="session")
def fallback_engine() -> RecommendationEngine:
    return RecommendationEngine.build(dataclasses.replace(settings, force_fallback=True))


@pytest.fixture(scope="session")
def client(semantic_engine) -> TestClient:
    with TestClient(create_app(engine=semantic_engine)) as test_client:
        yield test_client
