"""Download a real, freely licensed photo for every eligible product.

The catalog's own images are gone (every ``mainImage`` URL returns 404
NoSuchBucket), so the UI would otherwise show no photos at all. This script
searches Wikimedia Commons with a hand-written query per product title, saves
a 640 px thumbnail to ``frontend/public/product-images/<product_id>.jpg`` and
writes ``frontend/src/productImages.json`` with the file, author, licence and
source page of each photo, which the UI shows as the credit.

These are representative photos of the product type, not the vendor's own
product shots. The catalog data itself is never modified.

    python -m scripts.fetch_product_images            # fetch missing images
    python -m scripts.fetch_product_images --refresh  # re-fetch everything
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import time
from pathlib import Path

import httpx

from app.config import settings
from app.services.data_loader import load_catalog

ROOT = Path(__file__).resolve().parents[2]
IMAGE_DIR = ROOT / "frontend" / "public" / "product-images"
MANIFEST = ROOT / "frontend" / "src" / "productImages.json"
API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia's robot policy requires a descriptive User-Agent with a contact URL.
HEADERS = {"User-Agent": "OccasionGiftFinder/1.0 "
                         "(https://github.com/ayushsingh8252-git/Ayush-Singh-Emilo-Ventures-Submission) httpx"}
WIDTH = 640

# Search phrase per product title (lower-cased). Several catalog titles are
# vague ("PRINT", "for jewellery"), so the query describes what the listing sells.
QUERIES = {
    "gift wrapping": "gift wrapping paper ribbon present",
    "gift sets & bundles": "gift basket set",
    "wax seals & stickers": "wax seal stamp envelope",
    "gift boxes": "gift box ribbon",
    "gretting cards": "greeting card",
    "flower": "flower bouquet",
    "lilies": "lily flowers bouquet",
    "marigold": "marigold flowers",
    "tulips": "tulip bouquet",
    "rose": "red rose flower",
    "diwali dry fruits hampers": "dry fruits gift box",
    "holi dry fruits hampers": "dry fruits nuts bowl",
    "christmas dry fruits hampers": "christmas hamper",
    "holi luxury gift hampers": "gift hamper basket",
    "diwali luxury gift hampers": "diwali gift hamper",
    "christmas luxury gift hampers": "christmas gift basket",
    "print": "printed t-shirt",
    "bike and car printed": "printed t-shirt",
    "shirts": "men's shirt",
    "office wears": "formal office wear suit",
    "cargos": "cargo pants",
    "baggy jeans": "baggy jeans",
    "pants": "trousers clothing",
    "round neck tshirts": "t-shirt",
    "polo neck tshirts(women)": "polo shirt",
    "polo neck tshirts(men)": "polo shirt men",
    "kashmiri suits": "salwar kameez",
    "straigh fit kurtis": "kurti",
    "ready to wear sarees": "saree",
    "rose gold watch": "rose gold wristwatch",
    "metallic silver watch": "silver wristwatch",
    "black watch": "black wristwatch",
    "vintage watch": "vintage wristwatch",
    "rosegold watch": "women's wristwatch",
    "metallic gold watch": "gold wristwatch",
    "for jewellery": "jewellery necklace earrings",
    "gold choker necklave": "gold choker necklace",
    "multicolor choker necklace": "beaded necklace",
    "rosegold necklace": "pendant necklace",
    "silver layered nacklace": "silver necklace",
    "silver stone bracelet": "silver bracelet",
    "gold stacked bracelet": "gold bangles",
    "drop pearl bracelet": "pearl bracelet",
    "gold drop earrings": "gold earrings",
    "silver oxidized earings": "oxidised silver earrings jhumka",
    "rosegold studs earrings": "stud earrings",
    "bamboo lifestyle products": "bamboo products",
    "plant based candles": "soy candle",
    "natural fiber décor items": "jute basket",
    "indoor plants & planters": "indoor potted plant",
    "recycled paper notebooks & journals": "notebook journal",
    "recycled & upcycled gifts": "upcycled crafts",
    "upcycled fabric bags & pouches": "cloth tote bag",
    "self-care kits": "spa bath products",
    "health & fitness gifts": "dumbbells",
    "mental wellness gifts": "meditation candle relaxation",
    "rollerball pens": "rollerball pen",
    "fountain pens": "fountain pen",
    "metal pens": "metal ballpoint pen",
    "executive pens": "luxury pen",
    "floria perfume": "perfume bottle",
    "cherry blossom candle": "scented candle",
    "lavender candle": "lavender candle",
    "woodé soap": "handmade soap",
    "woodé perfume": "perfume bottles",
    "woodé solid perfumes": "solid perfume tin",
    "floria soap": "soap bars",
    "floria solid perfume": "perfume",
    "fresé perfume soap": "handmade soap bar",
    "fresé perfume": "fragrance bottle",
    "fresé solid perfume": "solid perfume",
    "dark chocolate": "dark chocolate bar",
    "white chocolates": "white chocolate",
    "organic skincare products": "skincare products cosmetics",
    "herbal teas & infusions": "herbal tea cup",
    "organic bath salts & scrubs": "bath salt",
    "arts & craft kits": "arts and crafts supplies",
    "diy slime kits": "slime toy",
    "painting & coloring kits": "watercolor paint set",
    "soft toys & plushies": "plush toys",
    "teddy bears": "teddy bear",
    "keychain plushies": "plush keychain",
    "drums & percussion sets": "toy drum",
    "xylophones": "xylophone",
    "dj & music mixer toys": "dj mixer",
    "toy guitars": "toy guitar",
    "forever rose": "preserved rose glass dome",
    "couple perfumes": "perfume bottles pair",
    "luxury chocolates": "chocolate box pralines",
    "body oils": "essential oil bottles",
    "snacks box": "snacks assortment",
    "custom star map": "star chart night sky",
    "personalized story book": "children's picture book",
    "couple mugs": "coffee mugs",
    "open when letters": "envelopes letters",
    "touch bracelets": "couple bracelets",
    "digital gift cards": "gift card",
    "physical gift cards": "gift cards",
    "open-value gift cards": "gift voucher",
    "seasonal gift cards": "christmas card",
    "engagement gift": "engagement ring",
    "housewarming gifts": "housewarming gift",
    "baby shower & newborn gifts": "baby clothes gift",
}

# Hand-checked photos for products whose top search result was wrong (a politician
# named Kurti for "Kurtis", a concert for "PRINT", ...). These win over QUERIES.
PINNED = {
    "baby shower & newborn gifts": "File:Knit baby booties - Flickr - normanack.jpg",
    "bamboo lifestyle products": "File:Humble Brush.jpg",
    "bike and car printed": "File:Wiki Loves Bangla T-Shirt Black.jpg",
    "christmas dry fruits hampers": "File:MixedNuts.JPG",
    "couple perfumes": "File:Perfume in small bottle.jpg",
    "digital gift cards": "File:Amazon.co.jp variable card in 2015 - 1.jpg",
    "diwali dry fruits hampers": "File:Walnuts pistachios cashew almonds.jpg",
    "diwali luxury gift hampers": "File:Gift-Hamper.png",
    "dj & music mixer toys": "File:CASIO XW-J1 DJ Controller (2015) powered by Vestax - 2015 NAMM Show.jpg",
    "drop pearl bracelet": "File:Pearl bracelet - a.JPG",
    "drums & percussion sets": "File:Child plays with toy drum in a bright room filled with books and toys during "
                               "afternoon light.jpg",
    "floria solid perfume": "File:Rain - Eau de Parfum, by Clean classic 2.jpg",
    "for jewellery": "File:Twisted wire jewelry (Unsplash).jpg",
    "forever rose": "File:Bouquet de roses doubles - Rosier buisson.jpg",
    "fresé solid perfume": "File:Flacon L'Origan 1905.jpg",
    "gift sets & bundles": "File:Engagement gifts basket (01).jpg",
    "gold drop earrings": "File:Gold Earrings, Kangra Himachal Pradesh.jpg",
    "gold stacked bracelet": "File:916 Bangles.jpg",
    "gretting cards": "File:PR29 Greetings cards addressed to Miss Stone.jpg",
    "holi dry fruits hampers": "File:Dry fruits shop.jpg",
    "holi luxury gift hampers": "File:Wrapped fruit basket.jpg",
    "housewarming gifts": "File:DFC 5982 A joyful porcelain Laughing Buddha surrounded by playful children flanked by "
                          "two ornate vases with floral arrangements - a charming display of prosperity and "
                          "happiness.jpg",
    "indoor plants & planters": "File:Modern faux plant in white pot on a kitchen countertop, enhancing decor.jpg",
    "kashmiri suits": "File:Shalwar kameez Colours.jpg",
    "lavender candle": "File:3set jars.jpg",
    "lilies": "File:Lilium candidum kz01.jpg",
    "mental wellness gifts": "File:Deep meditation in forest.jpg",
    "metal pens": "File:Parker Vector Stainless Steel Ballpoint Pen.jpg",
    "natural fiber décor items": "File:Ratan vases.jpg",
    "office wears": "File:Teba jacket.jpg",
    "open when letters": "File:Handwritten Letter of Resignation.jpg",
    "open-value gift cards": "File:SM gift card.jpg",
    "personalized story book": "File:Close-up of child reading a book.jpg",
    "print": "File:GlobeTeeGray.jpg",
    "ready to wear sarees": "File:Embroidery on a saree 01.jpg",
    "round neck tshirts": "File:BlueIEditShirt-plainBackground.jpeg",
    "silver oxidized earings": "File:Silver Dogri Jhumka with glass, possibly late 19th-early 20th century, "
                               "Bilaspur.jpg",
    "snacks box": "File:Namkeen in plastic cover from Uttarakhand (18).jpg",
    "straigh fit kurtis": "File:Shalwar kameez (1710606).jpg",
    "touch bracelets": "File:Friendship Bracelet special forms.jpg",
    "wax seals & stickers": "File:1778 wax seal of merchant guild in Sombor.jpg",
    "woodé solid perfumes": "File:Diptyque L'Ombre dans l'Eau EDP.jpg",
}
# Two different listings are both titled "Flower"; pin the second one by product ID.
PINNED_BY_ID = {"cmmxgiyuv0001v86gwypmc4am": "File:Bouquet de roses roses.jpg"}

# Commons results that are clearly not product photos.
SKIP_TITLE = re.compile(r"\b(map|logo|diagram|chart of|icon|flag|coat of arms|stamp of|poster|book cover)\b", re.I)


def save_jpeg(data: bytes, path: Path) -> None:
    """Store as a JPEG at most WIDTH px wide (Commons may serve larger or PNG thumbnails)."""
    from PIL import Image  # installed with sentence-transformers

    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((WIDTH, WIDTH))
    image.save(path, "JPEG", quality=82, optimize=True, progressive=True)


def _strip_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def search(client: httpx.Client, query: str, limit: int = 12) -> list[dict]:
    """Search Commons, or fetch one exact file when ``query`` is a "File:..." title.

    Free-text search is noisy, so products whose top result was wrong are pinned
    to a hand-checked file in QUERIES.
    """
    params = {"action": "query", "format": "json", "prop": "imageinfo",
              "iiprop": "url|size|extmetadata|mime", "iiurlwidth": WIDTH}
    exact = query.startswith("File:")
    if exact:
        params["titles"] = query
    else:
        params.update({"generator": "search", "gsrnamespace": 6, "gsrsearch": f"{query} filetype:bitmap",
                       "gsrlimit": limit})
    pages = client.get(API, params=params).json().get("query", {}).get("pages", {})
    results = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        width, height = info.get("width", 0), info.get("height", 0)
        if info.get("mime") not in {"image/jpeg", "image/png", "image/webp"} or not width or not height:
            continue
        if not exact and (SKIP_TITLE.search(page["title"]) or not 0.6 <= width / height <= 2.0 or width < 400):
            continue
        results.append({
            "commons_title": page["title"],
            "thumb_url": info.get("thumburl"),
            "source": info.get("descriptionurl"),
            "author": _strip_html(meta.get("Artist", {}).get("value", "")) or "Unknown",
            "license": _strip_html(meta.get("LicenseShortName", {}).get("value", "")) or "See source",
            "license_url": meta.get("LicenseUrl", {}).get("value"),
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="re-fetch images that already exist")
    parser.add_argument("--only", nargs="*", default=[], help="product IDs to (re)fetch")
    parser.add_argument("--skip", type=int, default=0, help="with --only: use the N-th search result instead")
    args = parser.parse_args()

    catalog = load_catalog(settings.data_path)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    used = {entry["commons_title"] for entry in manifest.values()}
    missing_queries = []

    with httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for product in catalog.eligible:
            pid = product.product_id
            if args.only and pid not in args.only:
                continue
            title = product.title.strip().lower()
            pinned = PINNED_BY_ID.get(pid) or PINNED.get(title)
            query = pinned or QUERIES.get(title)
            up_to_date = pid in manifest and (IMAGE_DIR / manifest[pid]["file"]).exists() and (
                not pinned or manifest[pid]["commons_title"] == pinned)
            if up_to_date and not (args.refresh or args.only):
                continue
            if not query:
                missing_queries.append(product.title)
                continue
            if pid in manifest:
                used.discard(manifest[pid]["commons_title"])
            candidates = [c for c in search(client, query) if c["commons_title"] not in used]
            candidates = candidates[args.skip:] if args.only else candidates
            if not candidates:
                print(f"  no result  {product.title!r} ({query!r})")
                continue
            choice = candidates[0]
            image = client.get(choice["thumb_url"])
            image.raise_for_status()
            file = f"{pid}.jpg"
            save_jpeg(image.content, IMAGE_DIR / file)
            used.add(choice["commons_title"])
            manifest[pid] = {"file": file, "product": product.title, "query": query,
                             **{k: v for k, v in choice.items() if k != "thumb_url"}}
            print(f"  ok  {product.title:<38} <- {choice['commons_title'][:60]}")
            time.sleep(0.3)  # be polite to the Commons API

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(manifest)} products have a photo; manifest: {MANIFEST.relative_to(ROOT)}")
    if missing_queries:
        print("No query defined for:", ", ".join(sorted(set(missing_queries))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
