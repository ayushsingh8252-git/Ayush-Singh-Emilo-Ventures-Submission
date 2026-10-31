"""Recommendation engine behaviour on the supplied catalog.

Relevance assertions check *properties* of the returned products (words in
their own title/description, inferred category) - never hard-coded IDs.
"""

from __future__ import annotations

import dataclasses
import re

import numpy as np
import pytest

from app.config import settings
from app.models.product import RecommendRequest
from app.services import embedding_service, vector_store
from app.services.data_loader import load_catalog_from_records
from app.services.embedding_service import MODE_TFIDF, TfidfEncoder, create_encoder
from app.services.recommendation_service import EMPTY_MESSAGE, RecommendationEngine
from app.services.vector_store import NumpyVectorStore, create_vector_store
from app.utils.scoring import calibrate_similarity, combine_scores, concept_relevance, keyword_relevance
from tests.conftest import make_record


def recommend(engine, occasion, **kwargs):
    return engine.recommend(RecommendRequest(occasion=occasion, **kwargs))


def text_of(rec) -> str:
    return f"{rec.name} {rec.short_description} {rec.description}".lower()


def mentions(rec, *words) -> bool:
    return any(re.search(rf"\b{w}", text_of(rec)) for w in words)


ROMANTIC = ("romantic", "romance", "love", "couple", "rose", "flower", "bouquet", "chocolate", "perfume",
            "necklace", "earring", "bracelet", "together")


# ------------------------------------------------------------ eligibility
@pytest.mark.parametrize("occasion", ["Valentine's Day", "Birthday", "Diwali", "chocolate", "perfume"])
def test_only_eligible_products_are_recommended(semantic_engine, catalog, occasion):
    eligible = {p.product_id for p in catalog.eligible}
    result = recommend(semantic_engine, occasion, limit=24)
    assert {r.product_id for r in result.recommendations} <= eligible


def test_review_required_chocolates_never_appear(semantic_engine, raw_catalog):
    blocked = {r["id"] for r in raw_catalog if r["status"] != "ACTIVE"}
    result = recommend(semantic_engine, "chocolate", limit=24)
    assert result.total_results > 0
    assert blocked.isdisjoint(r.product_id for r in result.recommendations)


# --------------------------------------------------------------- ranking
def test_valentines_day_recommends_romantic_products(semantic_engine):
    result = recommend(semantic_engine, "Valentine's Day")
    assert result.interpretation.matched_occasion == "Valentine's Day"
    assert result.total_results >= 8
    assert all(mentions(r, *ROMANTIC) for r in result.recommendations[:5])
    assert not any(r.category_label == "Toys & Kids" for r in result.recommendations)


def test_diwali_ranks_diwali_products_first(semantic_engine):
    result = recommend(semantic_engine, "Diwali")
    assert all("diwali" in r.name.lower() for r in result.recommendations[:2])
    assert all(mentions(r, "festiv", "festival", "hamper", "tradition", "heritage")
               for r in result.recommendations)


def test_child_query_returns_toys(semantic_engine):
    result = recommend(semantic_engine, "Gift for a child")
    assert result.total_results >= 8
    assert all(r.category_label == "Toys & Kids" for r in result.recommendations[:8])


def test_office_party_prefers_corporate_products(semantic_engine):
    top = recommend(semantic_engine, "Office Party").recommendations[:5]
    assert sum(mentions(r, "corporate", "office", "work", "pen", "professional") for r in top) >= 4


def test_occasion_named_for_another_event_is_demoted(semantic_engine):
    result = recommend(semantic_engine, "Birthday")
    names = [r.name for r in result.recommendations]
    assert not names[0].startswith("Baby Shower")


def test_scores_are_normalised_and_breakdown_is_reported(semantic_engine):
    for rec in recommend(semantic_engine, "Anniversary").recommendations:
        assert 0.0 <= rec.similarity_score <= 1.0
        for value in (rec.score_breakdown.semantic, rec.score_breakdown.keyword, rec.score_breakdown.concept):
            assert 0.0 <= value <= 1.0


def test_results_are_diverse_across_categories(semantic_engine):
    result = recommend(semantic_engine, "Valentine's Day")
    assert len({r.category_label for r in result.recommendations}) >= 4
    assert len({r.product_id for r in result.recommendations}) == result.total_results


def test_reasons_cite_words_from_the_listing(semantic_engine):
    for rec in recommend(semantic_engine, "Valentine's Day").recommendations:
        quoted = re.findall(r"“([^”]+)”", rec.reason)
        assert rec.reason.startswith("Recommended for Valentine's Day")
        listing = f"{rec.name} {rec.short_description} {rec.description}".lower()
        for phrase in quoted:
            assert phrase.lower().rstrip("…") in listing


# -------------------------------------------------- unknown / empty input
def test_unfamiliar_occasion_uses_semantic_retrieval(semantic_engine):
    result = recommend(semantic_engine, "Eid celebration")
    assert result.total_results > 0
    assert any("hamper" in r.name.lower() for r in result.recommendations[:3])


def test_nonsense_query_returns_meaningful_empty_state(semantic_engine):
    result = recommend(semantic_engine, "zzqx qwrtp")
    assert result.total_results == 0
    assert result.recommendations == []
    assert result.message == EMPTY_MESSAGE


def test_unmatched_topic_does_not_fill_grid_with_unrelated_products(semantic_engine):
    result = recommend(semantic_engine, "gaming laptop")
    assert result.total_results == 0


def test_empty_occasion_is_rejected_by_validation():
    with pytest.raises(ValueError):
        RecommendRequest(occasion="   ")


# ---------------------------------------------------------------- filters
def test_max_price_filter(semantic_engine):
    result = recommend(semantic_engine, "Valentine's Day", max_price=1000)
    assert result.total_results > 0
    assert all(r.final_price <= 1000 for r in result.recommendations)


def test_min_and_max_price_filter(semantic_engine):
    result = recommend(semantic_engine, "Wedding", min_price=1000, max_price=3000)
    assert all(1000 <= r.final_price <= 3000 for r in result.recommendations)


def test_budget_in_text_is_applied(semantic_engine):
    result = recommend(semantic_engine, "Something under ₹1,000")
    assert result.interpretation.applied_max_price == 1000
    assert result.total_results > 0
    assert all(r.final_price <= 1000 for r in result.recommendations)


def test_impossible_price_range_returns_filter_message(semantic_engine):
    result = recommend(semantic_engine, "Birthday", max_price=1)
    assert result.total_results == 0
    assert "filters" in result.message


def test_category_filter(semantic_engine):
    category = next(c for c in semantic_engine.categories() if c["label"] == "Jewellery")
    result = recommend(semantic_engine, "Anniversary", category=category["category_id"])
    assert result.total_results > 0
    assert all(r.category_id == category["category_id"] for r in result.recommendations)


def test_limit_is_respected(semantic_engine):
    assert recommend(semantic_engine, "Gift for a child", limit=3).total_results == 3


# ----------------------------------------------------- degenerate catalogs
def test_engine_with_no_eligible_products():
    catalog = load_catalog_from_records([make_record(status="DRAFT")])
    engine = RecommendationEngine.build(dataclasses.replace(settings, force_fallback=True), catalog=catalog)
    assert engine.health()["indexed_products"] == 0
    result = recommend(engine, "Birthday")
    assert result.total_results == 0
    assert "No eligible products" in result.message


def test_missing_image_is_returned_as_null(fallback_engine):
    catalog = load_catalog_from_records([make_record(mainImage="not a url")])
    engine = RecommendationEngine.build(dataclasses.replace(settings, force_fallback=True), catalog=catalog)
    rec = recommend(engine, "Valentine's Day").recommendations[0]
    assert rec.image_url is None


# --------------------------------------------------------------- fallback
def test_forced_fallback_reports_tfidf_mode(fallback_engine):
    health = fallback_engine.health()
    assert health["recommendation_mode"] == MODE_TFIDF
    assert health["embedding_model_status"] == "disabled"
    assert isinstance(fallback_engine.encoder, TfidfEncoder)


def test_fallback_still_recommends_relevant_products(fallback_engine):
    result = recommend(fallback_engine, "Valentine's Day")
    assert result.recommendation_mode == MODE_TFIDF
    assert result.total_results > 0
    assert all(mentions(r, *ROMANTIC) for r in result.recommendations[:5])


def test_model_load_failure_falls_back_to_tfidf(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("no internet")

    monkeypatch.setattr(embedding_service, "SentenceTransformerEncoder", boom)
    encoder, status, reason = create_encoder(["a rose bouquet"], "any-model", None, force_fallback=False)
    assert isinstance(encoder, TfidfEncoder)
    assert status == "unavailable"
    assert "no internet" in reason


def test_faiss_failure_falls_back_to_numpy(monkeypatch):
    def boom(*_args, **_kwargs):
        raise ImportError("faiss missing")

    monkeypatch.setattr(vector_store, "FaissVectorStore", boom)
    store, reason = create_vector_store(np.eye(3, dtype=np.float32))
    assert isinstance(store, NumpyVectorStore)
    assert "faiss missing" in reason
    assert store.search(np.array([0, 1, 0], dtype=np.float32), 1) == [(1, 1.0)]


def test_faiss_search_respects_allowed_ids():
    store, _ = create_vector_store(np.eye(4, dtype=np.float32))
    hits = store.search(np.array([1, 0, 0, 0], dtype=np.float32), 4, allowed={2, 3})
    assert {i for i, _ in hits} == {2, 3}


# ------------------------------------------------------------------ scoring
def test_scoring_components_are_bounded():
    assert calibrate_similarity(0.9, 0.1, 0.6) == 1.0
    assert calibrate_similarity(0.0, 0.1, 0.6) == 0.0
    fields = [(frozenset({"rose"}), 1.0), (frozenset({"rose", "love"}), 0.6)]
    score, terms = keyword_relevance(["rose", "unknownterm"], fields, {"rose": 2.0, "love": 1.0})
    assert score == 1.0 and terms == ["rose"]
    score, matched = concept_relevance({"romance": 1.0}, {"romance": ("love",)}, fields)
    assert score == pytest.approx(0.6) and matched == {"romance": ["love"]}


def test_uninformative_components_are_reweighted():
    w = settings.weights
    assert combine_scores(0.8, 0.0, 0.0, w, keyword_informative=False, concept_informative=False) == pytest.approx(0.8)
    full = combine_scores(1.0, 1.0, 1.0, w, True, True)
    assert full == pytest.approx(1.0)


# ------------------------------------------------- audit regressions (v1.1)
OTHER_OCCASION_TITLES = ("baby shower", "engagement", "housewarming", "diwali", "holi", "christmas")


@pytest.mark.parametrize("occasion", ["Birthday", "Graduation", "Mother's Day", "Father's Day"])
def test_products_titled_for_another_occasion_stay_out_of_the_top_five(semantic_engine, occasion):
    top = recommend(semantic_engine, occasion).recommendations[:5]
    assert not [r.name for r in top if any(w in r.name.lower() for w in OTHER_OCCASION_TITLES)]


def test_gift_add_ons_are_demoted_unless_requested(semantic_engine):
    add_on = re.compile(r"wrapping|wax seal|gift box", re.I)
    graduation = recommend(semantic_engine, "Graduation").recommendations[:5]
    assert not [r.name for r in graduation if add_on.search(r.name)]
    wrapping = recommend(semantic_engine, "gift wrapping and boxes").recommendations[:3]
    assert any(add_on.search(r.name) for r in wrapping)


def test_snacks_box_is_labelled_by_its_contents(catalog):
    from app.services.preprocessing import infer_product_category
    snacks = next(p for p in catalog.eligible if p.title == "Snacks Box")
    assert infer_product_category(snacks) == "Chocolates & Treats"


def test_faiss_scores_are_cosine_similarities(semantic_engine):
    vectors = semantic_engine.vectors
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-4)
    query = semantic_engine.encoder.encode(["romantic anniversary gift"])[0]
    for index, score in semantic_engine.store.search(query, 10):
        assert score == pytest.approx(float(vectors[index] @ query), abs=1e-5)


def test_add_on_detection_covers_catalog_add_ons(semantic_engine):
    flagged = {d.product.title for d, is_add_on in zip(semantic_engine.docs, semantic_engine._is_accessory) if is_add_on}
    assert {"Gift Boxes", "Gift Wrapping", "Wax Seals & Stickers"} <= flagged
    assert not flagged & {"Snacks Box", "Digital Gift Cards", "Gift Sets & Bundles"}


def test_engine_starts_from_an_empty_catalog_file(tmp_path):
    path = tmp_path / "products.json"
    path.write_text("[]", encoding="utf-8")
    engine = RecommendationEngine.build(dataclasses.replace(settings, data_path=path, force_fallback=True))
    health = engine.health()
    assert (health["total_products_loaded"], health["eligible_products"], health["indexed_products"]) == (0, 0, 0)
    assert recommend(engine, "Diwali").total_results == 0
