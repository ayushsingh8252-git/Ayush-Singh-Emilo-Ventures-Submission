"""Text normalisation, tokenisation and product-document construction.

The catalog only exposes opaque ``categoryId`` values, so a human-readable
category label is *inferred* from each product's own text using a small
keyword taxonomy. Labels are always surfaced as inferred in the API/UI.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from app.models.product import Product

_TOKEN = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    """
    a an and are as at be by for from has have in into is it its of on or our
    that the their this to was were will with your you we us each every every
    any all can just more most very so than too also some something gift gifts
    gifting perfect thoughtfully designed crafted made make ideal one item
    day days i me my for under over below above around want need looking buy
    """.split()
)


def fold(text: str) -> str:
    """Lower-case and strip accents (``WOODÉ`` -> ``woode``)."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def stem(token: str) -> str:
    """Very light plural stemmer; good enough for short catalog text."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ches", "shes", "sses", "xes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenize(text: str, *, drop_stopwords: bool = True) -> list[str]:
    tokens = _TOKEN.findall(fold(text).replace("'", ""))
    out = []
    for token in tokens:
        if drop_stopwords and token in STOPWORDS:
            continue
        if len(token) < 2:
            continue
        out.append(stem(token))
    return out


def slug_text(slug: str) -> str:
    return " ".join(w for w in re.split(r"[-_]+", slug or "") if w)


# --------------------------------------------------------------------------- #
# Inferred category taxonomy (label -> stemmed keywords)
# --------------------------------------------------------------------------- #
CATEGORY_TAXONOMY: dict[str, tuple[str, ...]] = {
    "Flowers": ("flower", "bouquet", "rose", "lily", "lilie", "tulip", "marigold", "bloom", "blossom", "floral"),
    "Chocolates & Treats": ("chocolate", "cocoa", "snack", "treat", "sweet"),
    "Jewellery": ("necklace", "nacklace", "bracelet", "earring", "earing", "jewel", "jewellery", "choker", "pearl", "stud"),
    "Watches": ("watch",),
    "Fragrances & Candles": ("perfume", "fragrance", "scent", "candle", "soap", "parfum", "aroma"),
    "Apparel": ("shirt", "tshirt", "jean", "pant", "cargo", "kurti", "kurtis", "saree", "suit", "wear", "clothe", "print", "polo"),
    "Festive Hampers": ("hamper", "dry", "fruit"),
    "Gift Cards": ("card",),
    "Gift Wrapping & Accessories": ("wrapping", "wrap", "box", "ribbon", "seal", "sticker", "bundle"),
    "Toys & Kids": ("toy", "plush", "plushie", "teddy", "kid", "slime", "craft", "xylophone", "drum", "guitar", "coloring", "painting"),
    "Wellness & Self-care": ("wellness", "self", "skincare", "bath", "tea", "fitness", "oil", "scrub", "salt", "health"),
    "Stationery": ("pen", "notebook", "journal"),
    "Eco Home & Decor": ("bamboo", "plant", "planter", "decor", "recycled", "upcycled", "eco"),
    "Personalised & Couple Gifts": ("personalized", "personalised", "custom", "star", "map", "couple", "letter", "mug", "storybook", "story"),
    "Life Event Gifts": ("engagement", "housewarming", "shower", "newborn", "baby"),
}
_FALLBACK_LABEL = "General Gifts"
GENERIC_CONTAINERS = frozenset({"box", "bundle"})


def infer_product_category(product: Product) -> str:
    """Pick the taxonomy label whose keywords best match the product.

    Title matches count three times as much as description matches because
    descriptions in this catalog are frequently templated/boiler-plate. The
    head noun (last taxonomy word in the title, e.g. "watch" in "Rose gold
    watch") gets an extra bonus so modifiers do not decide the label.
    """
    title_list = tokenize(product.title)
    title_tokens = set(title_list)
    all_keywords = {k for keywords in CATEGORY_TAXONOMY.values() for k in keywords}
    # Generic containers ("Snacks Box") never act as the head noun when the
    # title also names what is inside.
    candidates = [t for t in title_list if t in all_keywords]
    meaningful = [t for t in candidates if t not in GENERIC_CONTAINERS] or candidates
    head = meaningful[-1] if meaningful else None
    body_tokens = Counter(tokenize(f"{product.short_description} {product.description}"))
    best_label, best_score = _FALLBACK_LABEL, 0.0
    for label, keywords in CATEGORY_TAXONOMY.items():
        score = sum(3.0 for k in keywords if k in title_tokens)
        score += 2.0 if head in keywords else 0.0
        score += sum(min(body_tokens[k], 2) * 0.5 for k in keywords)
        if score > best_score:
            best_label, best_score = label, score
    return best_label


def infer_category_labels(products: list[Product]) -> dict[str, str]:
    """Label every category ID from the labels of its member products.

    Mixed categories get up to two labels joined with ' & '-style separators.
    """
    votes: dict[str, Counter] = defaultdict(Counter)
    for product in products:
        votes[product.category_id][infer_product_category(product)] += 1
    labels = {}
    for category_id, counter in votes.items():
        ranked = counter.most_common()
        top_label, top_count = ranked[0]
        total = sum(counter.values())
        if top_count / total >= 0.6 or len(ranked) == 1:
            labels[category_id] = top_label
        else:
            labels[category_id] = f"{top_label} · {ranked[1][0]}"
    return labels


# --------------------------------------------------------------------------- #
# Product documents
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ProductDocument:
    """Pre-computed text views of a product used by every ranking signal.

    ``shared_text`` holds vendor boilerplate (a short description copy-pasted
    across several listings). It describes the shop or product line rather
    than this product, so every signal weights it below product-specific text.
    """

    product: Product
    embedding_text: str  # product-specific text
    shared_text: str  # boilerplate, '' if none
    title_tokens: frozenset[str]
    body_tokens: frozenset[str]  # title + description words
    shared_tokens: frozenset[str]  # boilerplate-only tokens
    sentences: tuple[str, ...]  # description sentences, used for explanations


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
BOILERPLATE_MIN_LISTINGS = 3


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if len(s.strip()) > 15]


def find_boilerplate(products: list[Product]) -> set[str]:
    """Short descriptions repeated verbatim across several listings."""
    counts = Counter(p.short_description for p in products if p.short_description)
    return {text for text, n in counts.items() if n >= BOILERPLATE_MIN_LISTINGS}


def build_document(product: Product, boilerplate: frozenset[str] | set[str] = frozenset()) -> ProductDocument:
    short = product.short_description
    # Skip the short description when it is a (truncated) copy of the description.
    if short and product.description.startswith(short[:60]):
        short = ""
    shared = ""
    if short in boilerplate and product.description:
        shared, short = short, ""
    body = " ".join(d for d in (short, product.description) if d) or shared
    if body == shared:
        shared = ""
    parts = [
        f"{product.title}.",
        f"Category: {product.category_label}.",
        body,
        f"Brand: {product.brand}." if product.brand else "",
        f"Listing: {slug_text(product.slug)}." if product.slug else "",
    ]
    embedding_text = " ".join(p for p in parts if p)
    title_tokens = frozenset(tokenize(product.title))
    # Lexical signals only use words the listing itself contains, so that every
    # explanation can quote them. Brand/slug often hold shop names ("Petal & Oak",
    # "bloom by the hour") and stay in the embedding text only.
    body_tokens = frozenset(tokenize(body)) | title_tokens
    shared_tokens = frozenset(tokenize(shared)) - body_tokens
    sentences = tuple(split_sentences(product.description) or split_sentences(product.short_description))
    return ProductDocument(product, embedding_text, shared, title_tokens, body_tokens, shared_tokens, sentences)


def build_documents(products: list[Product]) -> list[ProductDocument]:
    """Attach inferred labels (per product), detect boilerplate, build documents."""
    boilerplate = find_boilerplate(products)
    docs = []
    for product in products:
        labelled = product.model_copy(update={"category_label": infer_product_category(product)})
        docs.append(build_document(labelled, boilerplate))
    return docs
