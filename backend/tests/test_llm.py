"""Optional LLM query-understanding layer. No test touches the network:
providers are faked, and the Gemini client runs on httpx.MockTransport."""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.models.product import RecommendRequest
from app.services.llm.providers import GeminiProvider, LLMError, LLMResult, create_provider
from app.services.llm.query_parser import RESPONSE_SCHEMA, SYSTEM_PROMPT, StructuredQuery, parse_query
from app.services.query_understanding import QueryUnderstandingService, extract_recipient_rules

EXAMPLE = {
    "occasion": "Valentine's Day",
    "recipient": "girlfriend",
    "min_price": 0,
    "max_price": 2000,
    "themes": ["romance", "flowers", "personalised"],
    "preferences": ["romantic", "thoughtful"],
}
EXAMPLE_QUERY = "Suggest a romantic gift for my girlfriend under ₹2,000."


class FakeProvider:
    """Returns a canned response (or raises) and records every call."""

    name = "fake"
    model = "fake-model"

    def __init__(self, data=None, error: LLMError | None = None):
        self.data, self.error, self.calls = data, error, []

    def generate_json(self, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        if self.error:
            raise self.error
        return LLMResult(data=self.data, model=self.model, latency_ms=5.0, input_tokens=400, output_tokens=60)


@pytest.fixture
def with_llm(semantic_engine, monkeypatch):
    """Swap the engine's understanding service for one backed by a given provider."""

    def install(provider, status="ready"):
        service = QueryUnderstandingService(semantic_engine.occasions, provider, status)
        monkeypatch.setattr(semantic_engine, "understanding", service)
        return service

    return install


def recommend(engine, text, **kwargs):
    return engine.recommend(RecommendRequest(query=text, **kwargs))


# ------------------------------------------------------- structured output
def test_llm_structured_output_drives_recommendations(semantic_engine, with_llm):
    with_llm(FakeProvider(EXAMPLE))
    result = recommend(semantic_engine, EXAMPLE_QUERY)
    it = result.interpretation
    assert it.understanding_mode == "llm"
    assert it.matched_occasion == "Valentine's Day"
    assert it.recipient == "girlfriend"
    assert it.applied_max_price == 2000
    assert {"romantic", "thoughtful"} <= set(it.preferences)
    assert {"romance and love", "flowers"} <= set(it.concepts)
    assert result.total_results > 0
    assert all(r.final_price <= 2000 for r in result.recommendations)


def test_structured_query_validation_and_sanitising():
    sq = StructuredQuery.model_validate({
        "occasion": "  Valentine's   Day ", "recipient": "null", "min_price": 3000, "max_price": 1000,
        "themes": ["romance", "Flowers", "not_a_theme", "personalized keepsakes", 7],
        "preferences": ["romantic", "romantic", "x" * 80, 5],
        "products": [{"name": "Fake Rolex", "price": 1}],  # invented data is dropped
    })
    assert sq.occasion == "Valentine's Day"
    assert sq.recipient is None
    assert (sq.min_price, sq.max_price) == (1000, 3000)  # inverted range swapped
    assert sq.themes == ["romance", "flowers", "personalised"]
    assert sq.preferences == ["romantic", "x" * 30]
    assert not hasattr(sq, "products")


def test_response_schema_restricts_themes_to_known_concepts():
    from app.services.occasion_service import CONCEPTS
    assert RESPONSE_SCHEMA["properties"]["themes"]["items"]["enum"] == list(CONCEPTS)


# --------------------------------------------------------- invalid output
@pytest.mark.parametrize("bad", [
    {"occasion": 42},                       # wrong type
    {"max_price": "lots of money"},         # non-numeric price
    {"min_price": True},                    # boolean price
])
def test_invalid_llm_output_falls_back_to_rules(semantic_engine, with_llm, bad):
    with_llm(FakeProvider(bad))
    result = recommend(semantic_engine, "Valentine's Day", use_llm=True)
    assert result.interpretation.understanding_mode == "rules"
    assert result.interpretation.llm_fallback_reason == "invalid_response"
    assert result.total_results > 0


def test_out_of_range_prices_are_ignored():
    sq = StructuredQuery.model_validate({"min_price": -50, "max_price": float("inf")})
    assert (sq.min_price, sq.max_price) == (None, None)


# ------------------------------------------------- timeout / errors / key
@pytest.mark.parametrize("kind", ["timeout", "http_error", "network", "invalid_response"])
def test_provider_errors_fall_back_with_identical_results(semantic_engine, with_llm, kind):
    rules_ids = [r.product_id for r in recommend(semantic_engine, "Anniversary", use_llm=False).recommendations]
    with_llm(FakeProvider(error=LLMError(kind)))
    result = recommend(semantic_engine, "Anniversary", use_llm=True)
    assert result.interpretation.understanding_mode == "rules"
    assert result.interpretation.llm_fallback_reason == kind
    assert [r.product_id for r in result.recommendations] == rules_ids


def test_missing_api_key_reports_status_and_uses_rules():
    provider, status, reason = create_provider(dataclasses.replace(settings, llm_enabled=True, gemini_api_key=""))
    assert provider is None and status == "missing_key"
    service = QueryUnderstandingService(None, None, status, reason)  # occasions unused below
    assert not service.llm_available


def test_missing_key_engine_still_recommends(semantic_engine, monkeypatch):
    monkeypatch.setattr(semantic_engine, "understanding",
                        QueryUnderstandingService(semantic_engine.occasions, None, "missing_key"))
    result = recommend(semantic_engine, EXAMPLE_QUERY, use_llm=True)
    assert result.interpretation.understanding_mode == "rules"
    assert result.interpretation.llm_fallback_reason == "missing_key"
    assert result.interpretation.applied_max_price == 2000  # rule-based budget still works
    assert result.total_results > 0


def test_llm_disabled_is_the_default_and_matches_rules(semantic_engine):
    assert semantic_engine.health()["llm"]["status"] == "disabled"
    result = recommend(semantic_engine, "Diwali")
    assert result.interpretation.understanding_mode == "rules"
    assert result.interpretation.llm_fallback_reason is None


def test_unsupported_provider_is_reported():
    _, status, _ = create_provider(dataclasses.replace(settings, llm_enabled=True, llm_provider="other",
                                                       gemini_api_key="x"))
    assert status == "unsupported_provider"


def test_per_request_override_skips_the_llm(semantic_engine, with_llm):
    provider = FakeProvider(EXAMPLE)
    with_llm(provider)
    result = recommend(semantic_engine, EXAMPLE_QUERY, use_llm=False)
    assert result.interpretation.understanding_mode == "rules"
    assert provider.calls == []


# ------------------------------------------------------ budget / recipient
def test_rule_budget_wins_over_conflicting_llm_budget(semantic_engine, with_llm):
    with_llm(FakeProvider({**EXAMPLE, "max_price": 9999}))
    assert recommend(semantic_engine, EXAMPLE_QUERY).interpretation.applied_max_price == 2000


def test_llm_budget_used_when_rules_cannot_parse_it(semantic_engine, with_llm):
    with_llm(FakeProvider({**EXAMPLE, "min_price": None, "max_price": 1500}))
    it = recommend(semantic_engine, "romantic gift, can spend fifteen hundred at most").interpretation
    assert it.applied_max_price == 1500


def test_llm_cannot_invent_a_budget(semantic_engine, with_llm):
    with_llm(FakeProvider({**EXAMPLE, "max_price": 500}))
    it = recommend(semantic_engine, "a cheap romantic gift for my girlfriend").interpretation
    assert it.applied_max_price is None  # no amount in the shopper's words


@pytest.mark.parametrize("text, expected", [
    ("gift for my mom", "mother"), ("something for my girlfriend", "girlfriend"),
    ("present for a colleague", "colleague"), ("toy for my son", "son"), ("Diwali", None),
])
def test_rule_based_recipient_extraction(text, expected):
    assert extract_recipient_rules(text) == expected


def test_llm_recipient_adds_themes_without_changing_the_title(semantic_engine, with_llm):
    with_llm(FakeProvider({"occasion": "Birthday", "recipient": "mother", "min_price": None,
                           "max_price": None, "themes": [], "preferences": []}))
    it = recommend(semantic_engine, "birthday gift for mom").interpretation
    assert it.matched_occasion == "Birthday"
    assert it.recipient == "mother"
    assert "wellness and self-care" in it.concepts  # borrowed from the mother cue


def test_unknown_occasion_is_kept_as_a_label(semantic_engine, with_llm):
    with_llm(FakeProvider({"occasion": "Job Promotion", "recipient": "friend", "min_price": None,
                           "max_price": None, "themes": ["watches", "stationery"], "preferences": []}))
    result = recommend(semantic_engine, "my friend just got promoted")
    assert result.interpretation.matched_occasion == "Job Promotion"
    assert result.total_results > 0


# ------------------------------------------------------- product grounding
def test_llm_cannot_inject_products_or_facts(semantic_engine, with_llm, catalog):
    poisoned = {**EXAMPLE, "products": [{"product_id": "fake-1", "name": "Fake Rolex", "price": 1, "stock": 999,
                                         "isApproved": True}], "price": 1, "stock": 0}
    with_llm(FakeProvider(poisoned))
    result = recommend(semantic_engine, EXAMPLE_QUERY, limit=24)
    eligible = {p.product_id: p for p in catalog.eligible}
    assert result.total_results > 0
    for rec in result.recommendations:
        source = eligible[rec.product_id]  # KeyError if an ID were invented
        assert rec.name == source.title
        assert rec.price == source.price
        assert rec.stock == source.stock
        assert rec.final_price == source.final_price
    assert "Fake Rolex" not in json.dumps(result.model_dump())


def test_llm_never_receives_catalog_data(semantic_engine, with_llm, catalog):
    provider = FakeProvider(EXAMPLE)
    with_llm(provider)
    recommend(semantic_engine, "Holi gift ideas")
    sent = provider.calls[0]["system"] + provider.calls[0]["user"]
    assert not [p.title for p in catalog.eligible if len(p.title) > 8 and p.title in sent]
    assert "Shopper request: Holi gift ideas" in provider.calls[0]["user"]


def test_responses_are_cached_per_query(semantic_engine, with_llm):
    provider = FakeProvider(EXAMPLE)
    with_llm(provider)
    recommend(semantic_engine, EXAMPLE_QUERY)
    recommend(semantic_engine, "  suggest a ROMANTIC gift for my girlfriend under ₹2,000 ")
    assert len(provider.calls) == 1


# ------------------------------------------------------------- regression
@pytest.mark.parametrize("occasion, must_contain", [("Diwali", "diwali"), ("Christmas", "christmas")])
def test_llm_mode_keeps_existing_ranking_quality(semantic_engine, with_llm, occasion, must_contain):
    with_llm(FakeProvider({"occasion": occasion, "recipient": None, "min_price": None, "max_price": None,
                           "themes": ["festive", "hampers"], "preferences": []}))
    top = recommend(semantic_engine, occasion, use_llm=True).recommendations[:2]
    assert all(must_contain in r.name.lower() for r in top)


# ---------------------------------------------------------- Gemini client
def _gemini(handler):
    return GeminiProvider("test-key-123", "gemini-test", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_gemini_request_format_and_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(request.url), request.headers, json.loads(request.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(EXAMPLE)}]}}],
            "usageMetadata": {"promptTokenCount": 466, "candidatesTokenCount": 73},
        })

    sq, result = parse_query(_gemini(handler), EXAMPLE_QUERY)
    assert "test-key-123" not in seen["url"]  # key travels in a header, not the URL
    assert seen["headers"]["x-goog-api-key"] == "test-key-123"
    assert seen["url"].endswith("/models/gemini-test:generateContent")
    config = seen["body"]["generationConfig"]
    assert config["responseMimeType"] == "application/json" and config["temperature"] == 0
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == SYSTEM_PROMPT
    assert sq.recipient == "girlfriend" and sq.max_price == 2000
    assert (result.input_tokens, result.output_tokens) == (466, 73)
    assert "test-key-123" not in repr(_gemini(handler))


@pytest.mark.parametrize("response, kind", [
    (httpx.Response(500, json={"error": {"message": "boom"}}), "http_error"),
    (httpx.Response(429, json={}), "rate_limited"),
    (httpx.Response(503, json={}), "http_error"),
    (httpx.Response(200, json={"candidates": []}), "invalid_response"),
    (httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}), "invalid_response"),
    (httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "[1, 2]"}]}}]}), "invalid_response"),
])
def test_gemini_error_handling(response, kind):
    with pytest.raises(LLMError) as err:
        _gemini(lambda request: response).generate_json("s", "u", {})
    assert err.value.kind == kind


def test_gemini_timeout_is_reported_as_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMError) as err:
        _gemini(handler).generate_json("s", "u", {})
    assert err.value.kind == "timeout"


def test_gemini_requires_a_key():
    with pytest.raises(LLMError) as err:
        GeminiProvider("", "gemini-test")
    assert err.value.kind == "missing_key"


# -------------------------------------------------------------------- API
def test_api_accepts_natural_language_query(semantic_engine, with_llm):
    with_llm(FakeProvider(EXAMPLE))
    with TestClient(create_app(engine=semantic_engine)) as client:
        body = client.post("/api/recommend", json={"query": EXAMPLE_QUERY, "limit": 5}).json()
        health = client.get("/api/health").json()
    it = body["interpretation"]
    assert body["occasion"] == EXAMPLE_QUERY
    assert it["understanding_mode"] == "llm" and it["llm_provider"] == "fake"
    assert it["matched_occasion"] == "Valentine's Day"
    assert it["recipient"] == "girlfriend"
    assert it["applied_max_price"] == 2000
    assert it["preferences"] == ["romantic", "thoughtful"]
    for rec in body["recommendations"]:
        assert {"similarity_score", "score_breakdown", "reason"} <= rec.keys()
    assert health["llm"]["status"] == "ready"


def test_api_still_accepts_the_occasion_field(client):
    body = client.post("/api/recommend", json={"occasion": "Diwali", "use_llm": False}).json()
    assert body["interpretation"]["understanding_mode"] == "rules"
    assert body["total_results"] > 0


def test_api_rejects_empty_query_and_occasion(client):
    response = client.post("/api/recommend", json={"query": "  ", "occasion": ""})
    assert response.status_code == 422
    assert "empty" in response.json()["detail"].lower()


# --------------------------------------------------------- circuit breaker
def test_circuit_breaker_skips_llm_after_repeated_failures(semantic_engine, with_llm):
    from app.services import query_understanding as qu

    provider = FakeProvider(error=LLMError("timeout"))
    service = with_llm(provider)
    now = [1000.0]
    service.clock = lambda: now[0]
    for i in range(qu.CIRCUIT_FAILURE_THRESHOLD):
        assert recommend(semantic_engine, f"Birthday {i}").interpretation.llm_fallback_reason == "timeout"
    calls = len(provider.calls)
    result = recommend(semantic_engine, "wedding gift ideas")  # circuit is open: no call, instant fallback
    assert result.interpretation.llm_fallback_reason == "circuit_open"
    assert len(provider.calls) == calls
    assert result.total_results > 0

    now[0] += qu.CIRCUIT_COOLDOWN_SECONDS + 1  # cooldown over: the LLM is tried again
    provider.error, provider.data = None, EXAMPLE
    assert recommend(semantic_engine, EXAMPLE_QUERY).interpretation.understanding_mode == "llm"
    assert service._consecutive_failures == 0


# ----------------------------------------------------------------- routing
def test_exact_occasion_names_skip_the_llm(semantic_engine, with_llm):
    provider = FakeProvider(EXAMPLE)
    with_llm(provider)
    it = recommend(semantic_engine, "Father's Day").interpretation
    assert provider.calls == []
    assert it.understanding_mode == "rules" and it.understanding_route == "rules_exact_match"
    assert it.llm_fallback_reason is None


def test_explicit_use_llm_forces_the_llm_even_for_exact_names(semantic_engine, with_llm):
    provider = FakeProvider({**EXAMPLE, "occasion": "Father's Day"})
    with_llm(provider)
    it = recommend(semantic_engine, "Father's Day", use_llm=True).interpretation
    assert len(provider.calls) == 1 and it.understanding_route == "llm"


def test_free_text_queries_go_to_the_llm(semantic_engine, with_llm):
    provider = FakeProvider(EXAMPLE)
    with_llm(provider)
    assert recommend(semantic_engine, EXAMPLE_QUERY).interpretation.understanding_route == "llm"
    assert len(provider.calls) == 1


def test_llm_minimum_price_needs_lower_bound_wording(semantic_engine, with_llm):
    with_llm(FakeProvider({**EXAMPLE, "min_price": 800, "max_price": 1200}))
    it = recommend(semantic_engine, "housewarming for a friend who loves plants, around 1000").interpretation
    assert (it.applied_min_price, it.applied_max_price) == (None, 1200)
    with_llm(FakeProvider({**EXAMPLE, "min_price": 800, "max_price": 1200}))
    it = recommend(semantic_engine, "housewarming gift, at least eight hundred, at most twelve hundred").interpretation
    assert (it.applied_min_price, it.applied_max_price) == (800, 1200)


def test_preferences_that_repeat_occasion_or_recipient_are_dropped():
    sq = StructuredQuery.model_validate({"occasion": "Housewarming", "recipient": "mother",
                                         "preferences": ["Mother", "housewarming", "plants"]})
    assert sq.preferences == ["plants"]
