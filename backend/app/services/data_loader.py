"""Load the raw catalog, normalise every record and apply eligibility rules.

The raw ``products.json`` is never modified. Each record is converted into a
:class:`~app.models.product.Product`; malformed values are coerced to safe
defaults instead of crashing the load.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from app.models.product import Product

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")


@dataclass
class CatalogLoadResult:
    total_records: int = 0
    products: list[Product] = field(default_factory=list)  # all valid, de-duplicated
    eligible: list[Product] = field(default_factory=list)
    rejected: Counter = field(default_factory=Counter)  # reason -> count
    duplicates_removed: int = 0


# --------------------------------------------------------------------------- #
# Field coercion helpers
# --------------------------------------------------------------------------- #
def clean_text(value: Any) -> str:
    """Return a single-line, trimmed string ('' for None/non-text)."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return _WHITESPACE.sub(" ", str(value)).strip()


def parse_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_price(value: Any) -> Optional[float]:
    number = parse_float(value)
    return round(number, 2) if number is not None and number > 0 else None


def parse_discount(value: Any) -> float:
    number = parse_float(value)
    if number is None or number < 0:
        return 0.0
    return round(min(number, 100.0), 2)


def parse_int(value: Any) -> int:
    number = parse_float(value)
    return int(number) if number is not None else 0


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    if isinstance(value, (int, float)):
        return value == 1
    return False


def parse_image_url(value: Any) -> Optional[str]:
    url = clean_text(value)
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def title_from_slug(slug: str) -> str:
    words = [w for w in re.split(r"[-_\s]+", slug) if w]
    return " ".join(words[:6]).title()


def _first(raw: dict, *keys: str) -> Any:
    """Return the first non-empty value among alternative field names.

    Supports both the real catalog schema (``id``, ``name`` ...) and the
    payload schema from the assignment brief (``product_id``, ``title`` ...).
    """
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _image_from_files(raw: dict) -> Any:
    files = raw.get("files")
    if isinstance(files, list):
        for item in files:
            candidate = item.get("url") if isinstance(item, dict) else item
            if parse_image_url(candidate):
                return candidate
    return None


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
def normalize_record(raw: Any) -> tuple[Optional[Product], Optional[str]]:
    """Convert one raw record. Returns (product, None) or (None, reject_reason)."""
    if not isinstance(raw, dict):
        return None, "not_an_object"

    product_id = clean_text(_first(raw, "id", "product_id", "productId"))
    if not product_id:
        return None, "missing_id"

    slug = clean_text(raw.get("slug"))
    title = clean_text(_first(raw, "name", "title"))
    if not title:
        title = title_from_slug(slug)
    if not title:
        return None, "missing_title"

    status = clean_text(raw.get("status")).upper()
    deleted_at = raw.get("deletedAt")

    product = Product(
        product_id=product_id,
        vendor_id=clean_text(_first(raw, "shopId", "vendor_id", "vendorId")),
        category_id=clean_text(_first(raw, "categoryId", "vendor_category")),
        product_group_id=clean_text(raw.get("productGroupId")),
        title=title,
        slug=slug,
        description=clean_text(raw.get("description")),
        short_description=clean_text(raw.get("shortDescription")),
        brand=clean_text(raw.get("brand")),
        sku=clean_text(raw.get("sku")),
        image_url=parse_image_url(_first(raw, "mainImage") or _image_from_files(raw)),
        price=parse_price(raw.get("price")),
        discount_percentage=parse_discount(raw.get("discountPercentage")),
        stock=max(parse_int(raw.get("stock")), 0),
        is_approved=parse_bool(raw.get("isApproved")),
        status=status,
        deleted_at=clean_text(deleted_at) or None,
    )
    return product, None


def eligibility_failure(product: Product) -> Optional[str]:
    """Return why a product must not be recommended, or None if eligible."""
    if not product.is_approved:
        return "not_approved"
    if product.status != "ACTIVE":
        return f"status_{product.status.lower() or 'missing'}"
    if product.deleted_at is not None:
        return "deleted"
    if product.stock <= 0:
        return "out_of_stock"
    return None


def _dedupe(records: Iterable[tuple[Product, str]]) -> tuple[list[Product], int]:
    """Keep one product per ID, preferring the most recently updated record."""
    best: dict[str, tuple[Product, str]] = {}
    duplicates = 0
    for product, updated_at in records:
        existing = best.get(product.product_id)
        if existing is None:
            best[product.product_id] = (product, updated_at)
            continue
        duplicates += 1
        if updated_at > existing[1]:
            best[product.product_id] = (product, updated_at)
    return [p for p, _ in best.values()], duplicates


def load_catalog_from_records(records: Any) -> CatalogLoadResult:
    if isinstance(records, dict):  # tolerate {"products": [...]} wrappers
        records = records.get("products", [])
    if not isinstance(records, list):
        raise ValueError("Catalog JSON must be a list of product objects.")

    result = CatalogLoadResult(total_records=len(records))
    normalised: list[tuple[Product, str]] = []
    for raw in records:
        product, reason = normalize_record(raw)
        if product is None:
            result.rejected[reason] += 1
            continue
        normalised.append((product, clean_text(raw.get("updatedAt"))))

    result.products, result.duplicates_removed = _dedupe(normalised)
    if result.duplicates_removed:
        result.rejected["duplicate_id"] += result.duplicates_removed

    for product in result.products:
        reason = eligibility_failure(product)
        if reason:
            result.rejected[reason] += 1
        else:
            result.eligible.append(product)

    logger.info(
        "Catalog loaded: %d records, %d valid, %d eligible, rejected=%s",
        result.total_records,
        len(result.products),
        len(result.eligible),
        dict(result.rejected),
    )
    return result


def load_catalog(path: Path) -> CatalogLoadResult:
    with Path(path).open(encoding="utf-8") as fh:
        records = json.load(fh)
    return load_catalog_from_records(records)
