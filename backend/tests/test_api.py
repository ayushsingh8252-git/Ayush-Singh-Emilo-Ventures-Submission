"""HTTP API contract."""

from __future__ import annotations

from app.services.embedding_service import MODE_SEMANTIC


def test_health_reports_catalog_and_model_state(client, catalog):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["total_products_loaded"] == catalog.total_records
    assert body["eligible_products"] == len(catalog.eligible)
    assert body["indexed_products"] == len(catalog.eligible)
    assert body["recommendation_mode"] == MODE_SEMANTIC
    assert body["embedding_model_status"] == "loaded"
    assert body["vector_store"] == "faiss"


def test_occasions_endpoint(client):
    body = client.get("/api/occasions").json()
    assert {"Birthday", "Wedding", "Diwali", "Valentine's Day", "Anniversary", "Office Party"} <= set(body["occasions"])
    assert body["examples"]


def test_categories_endpoint_labels_are_marked_inferred(client, catalog):
    categories = client.get("/api/categories").json()["categories"]
    assert sum(c["product_count"] for c in categories) == len(catalog.eligible)
    assert all(c["label_is_inferred"] for c in categories)


def test_recommend_response_structure(client):
    response = client.post("/api/recommend", json={"occasion": "Valentine's Day", "limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["occasion"] == "Valentine's Day"
    assert body["total_results"] == len(body["recommendations"]) == 5
    assert body["recommendation_mode"] == MODE_SEMANTIC
    assert body["interpretation"]["matched_occasion"] == "Valentine's Day"
    expected_fields = {
        "product_id", "name", "description", "short_description", "brand", "category_id", "category_label",
        "image_url", "price", "final_price", "discount_percentage", "stock", "similarity_score",
        "score_breakdown", "matched_concepts", "reason",
    }
    for rec in body["recommendations"]:
        assert expected_fields <= rec.keys()
        assert rec["image_url"].startswith("https://")
        assert rec["reason"]


def test_recommend_with_filters(client):
    body = client.post("/api/recommend", json={"occasion": "Birthday", "max_price": 800}).json()
    assert all(r["final_price"] <= 800 for r in body["recommendations"])


def test_empty_state_response(client):
    body = client.post("/api/recommend", json={"occasion": "zzqx qwrtp"}).json()
    assert body["total_results"] == 0
    assert body["message"] == "No relevant products found for this occasion. Try another occasion."


def test_empty_occasion_is_422(client):
    for occasion in ("", "    "):
        response = client.post("/api/recommend", json={"occasion": occasion})
        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()


def test_missing_occasion_is_422(client):
    assert client.post("/api/recommend", json={}).status_code == 422


def test_invalid_limit_and_price_range_are_422(client):
    assert client.post("/api/recommend", json={"occasion": "Birthday", "limit": 0}).status_code == 422
    assert client.post("/api/recommend", json={"occasion": "Birthday", "limit": 500}).status_code == 422
    assert client.post("/api/recommend", json={"occasion": "Birthday", "min_price": -1}).status_code == 422
    response = client.post("/api/recommend", json={"occasion": "Birthday", "min_price": 900, "max_price": 100})
    assert response.status_code == 422


def test_cors_allows_the_vite_dev_server(client):
    response = client.options(
        "/api/recommend",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_malformed_json_is_422_without_bogus_field(client):
    response = client.post("/api/recommend", content=b'{"occasion":', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == ""


def test_unknown_category_returns_filter_message(client):
    body = client.post("/api/recommend", json={"occasion": "Birthday", "category": "does-not-exist"}).json()
    assert body["total_results"] == 0
    assert "filters" in body["message"]


def test_cors_rejects_unknown_origins(client):
    response = client.options(
        "/api/recommend",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in response.headers
