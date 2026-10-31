"""Catalog loading, normalisation and eligibility filtering."""

from __future__ import annotations

from app.services.data_loader import load_catalog_from_records, normalize_record
from app.services.preprocessing import build_documents, find_boilerplate, infer_product_category
from tests.conftest import make_record


# ---------------------------------------------------------------- real data
def test_loads_every_record_of_the_supplied_catalog(raw_catalog, catalog):
    assert catalog.total_records == len(raw_catalog)
    assert len(catalog.products) == len({r["id"] for r in raw_catalog})


def test_only_approved_active_undeleted_in_stock_products_are_eligible(raw_catalog, catalog):
    expected = {
        r["id"] for r in raw_catalog
        if r["isApproved"] is True and r["status"] == "ACTIVE" and r["deletedAt"] is None and r["stock"] > 0
    }
    assert {p.product_id for p in catalog.eligible} == expected
    assert all(p.status == "ACTIVE" and p.is_approved for p in catalog.eligible)


def test_draft_and_review_required_products_are_rejected(raw_catalog, catalog):
    blocked = {r["id"] for r in raw_catalog if r["status"] in {"DRAFT", "REVIEW_REQUIRED"}}
    assert blocked, "the supplied catalog contains DRAFT/REVIEW_REQUIRED records"
    assert blocked.isdisjoint(p.product_id for p in catalog.eligible)
    assert sum(catalog.rejected.values()) == catalog.total_records - len(catalog.eligible)


# ------------------------------------------------------------ normalisation
def test_normalisation_maps_catalog_fields():
    product, reason = normalize_record(make_record())
    assert reason is None
    assert product.product_id == "p-1"
    assert product.vendor_id == "shop-1"
    assert product.category_id == "cat-1"
    assert product.title == "Test Rose Bouquet"
    assert product.price == 999.0
    assert product.discount_percentage == 10.0
    assert product.final_price == 899.1
    assert product.image_url == "https://example.com/rose.png"


def test_assignment_payload_schema_is_also_supported():
    product, _ = normalize_record({
        "productId": 7, "vendorId": "v", "vendor_category": "c", "title": "Mug",
        "description": "A mug", "files": [{"url": "https://example.com/m.jpg"}],
        "isApproved": True, "status": "ACTIVE", "stock": 1,
    })
    assert (product.product_id, product.vendor_id, product.category_id) == ("7", "v", "c")
    assert product.image_url == "https://example.com/m.jpg"


def test_incorrect_types_and_invalid_values_are_coerced():
    product, _ = normalize_record(make_record(
        price="abc", discountPercentage="-5", stock="12", isApproved="true", name="  Spaced   name ",
    ))
    assert product.price is None
    assert product.final_price is None
    assert product.discount_percentage == 0.0
    assert product.stock == 12
    assert product.is_approved is True
    assert product.title == "Spaced name"


def test_invalid_or_missing_image_url_becomes_none():
    for value in ("not-a-url", "", None, "ftp://example.com/x.png", "/relative/path.png"):
        product, _ = normalize_record(make_record(mainImage=value))
        assert product.image_url is None, value


def test_missing_description_is_handled():
    result = load_catalog_from_records([make_record(description=None, shortDescription=None)])
    assert result.eligible[0].description == ""
    docs = build_documents(result.eligible)
    assert docs[0].embedding_text.startswith("Test Rose Bouquet.")


def test_missing_name_falls_back_to_slug_or_rejects():
    product, _ = normalize_record(make_record(name="", slug="silver-cuff-bracelet"))
    assert product.title == "Silver Cuff Bracelet"
    product, reason = normalize_record(make_record(name=None, slug=""))
    assert product is None and reason == "missing_title"


def test_missing_id_and_non_object_records_are_rejected():
    result = load_catalog_from_records([make_record(id=None), "garbage", 42])
    assert result.eligible == []
    assert result.rejected["missing_id"] == 1
    assert result.rejected["not_an_object"] == 2


# ----------------------------------------------------------------- filters
def test_status_approval_deletion_and_stock_filters():
    result = load_catalog_from_records([
        make_record(id="ok"),
        make_record(id="draft", status="DRAFT"),
        make_record(id="review", status="REVIEW_REQUIRED", isApproved=False),
        make_record(id="unapproved", isApproved=False),
        make_record(id="deleted", deletedAt="2026-02-01T00:00:00Z"),
        make_record(id="no-stock", stock=0),
        make_record(id="neg-stock", stock=-3),
    ])
    assert [p.product_id for p in result.eligible] == ["ok"]
    assert result.rejected["status_draft"] == 1
    assert result.rejected["not_approved"] == 2
    assert result.rejected["deleted"] == 1
    assert result.rejected["out_of_stock"] == 2


def test_duplicate_ids_keep_the_most_recently_updated_record():
    result = load_catalog_from_records([
        make_record(id="dup", name="Old name", updatedAt="2026-01-01T00:00:00Z"),
        make_record(id="dup", name="New name", updatedAt="2026-03-01T00:00:00Z"),
    ])
    assert len(result.products) == 1
    assert result.products[0].title == "New name"
    assert result.duplicates_removed == 1
    assert result.rejected["duplicate_id"] == 1


def test_no_eligible_products():
    result = load_catalog_from_records([make_record(status="DRAFT"), make_record(id="x", stock=0)])
    assert result.eligible == []
    assert len(result.products) == 2


# -------------------------------------------------------------- preprocess
def test_category_is_inferred_from_the_head_noun():
    rose_watch, _ = normalize_record(make_record(name="Rose gold watch", description="A wrist watch."))
    candle, _ = normalize_record(make_record(name="Cherry Blossom Candle", description="A scented candle."))
    assert infer_product_category(rose_watch) == "Watches"
    assert infer_product_category(candle) == "Fragrances & Candles"


def test_boilerplate_short_descriptions_are_detected(catalog):
    boilerplate = find_boilerplate(catalog.eligible)
    assert any(text.startswith("Personal Celebrations") for text in boilerplate)
    docs = build_documents(catalog.eligible)
    baby = next(d for d in docs if d.product.title.startswith("Baby Shower"))
    assert baby.shared_text.startswith("Personal Celebrations")
    assert "Personal Celebrations" not in baby.embedding_text
