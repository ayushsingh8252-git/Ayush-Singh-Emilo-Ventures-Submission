"""Hand-written relevance judgments for offline evaluation.

These are *my* gifting judgments (written by the author, not ground truth from
users), expressed as title patterns over the real catalog so they are easy to
review and challenge:

* grade 2 - a natural, core gift for the occasion
* grade 1 - acceptable / reasonable
* grade 0 - everything else, and always:
    - products whose title names a *different* occasion (e.g. a "Holi" hamper for Diwali)
    - gift add-ons (wrapping, wax seals, gift boxes) - they accompany a gift

Caveat: the same person wrote the occasion concept library, so these labels
are not independent of the model. They are used to compare configurations
against each other, not to claim an absolute accuracy.
"""

from __future__ import annotations

import re

OCCASION_TITLE_WORDS = {
    "diwali": "Diwali", "holi": "Holi", "christmas": "Christmas", "baby shower": "Baby Shower",
    "newborn": "Baby Shower", "engagement": "Wedding", "housewarming": "Housewarming",
}
ADD_ONS = re.compile(r"wrapping|wax seal|sticker|gift box|ribbon", re.I)

FLOWERS = r"flower|rose\b|lil(y|ies)|tulip|marigold|bouquet"
JEWELLERY = r"necklace|nacklace|bracelet|earring|earing|choker|jewel"
KIDS = r"teddy|plush|toy|xylophone|drum|guitar|craft|slime|painting"
WELLNESS = r"self-care|wellness|fitness|skincare|bath|herbal tea|body oil"

JUDGMENTS: dict[str, dict[str, str]] = {
    "Birthday": {
        "core": rf"{FLOWERS}|chocolate|perfume|watch|{JEWELLERY}|star map|story book|{KIDS}|snacks|candle",
        "ok": rf"gift card|mug|letters|{WELLNESS}|plant|gretting|greeting|tshirt|polo|gift sets|soap",
    },
    "Wedding": {
        "core": rf"couple|{JEWELLERY}|saree|kashmiri|kurti|star map|story book|perfume|forever rose|gift sets",
        "ok": rf"{FLOWERS}|candle|plant|decor|watch|chocolate|gift card|engagement",
    },
    "Valentine's Day": {
        "core": rf"couple|{FLOWERS}|chocolate|perfume|{JEWELLERY}|star map|story book|letters|body oil|teddy",
        "ok": r"candle|watch|gift card|snacks|mug|soap",
    },
    "Diwali": {
        "core": r"diwali|candle|saree|kashmiri|kurti|choker|decor|marigold",
        "ok": rf"chocolate|gift sets|gift card|{JEWELLERY}|plant|bamboo|snacks|dry fruit",
    },
    "Anniversary": {
        "core": rf"couple|{FLOWERS}|{JEWELLERY}|watch|star map|story book|perfume|letters|chocolate",
        "ok": r"candle|body oil|gift card|gift sets|snacks|mug",
    },
    "Office Party": {
        "core": r"\bpens?\b|notebook|journal|self-care|wellness|fitness|gift card|office",
        "ok": r"watch|chocolate|snacks|plant|mug|candle|herbal tea|shirt",
    },
    "Father's Day": {
        "core": r"watch|\bpens?\b|shirt|polo neck tshirts\(men\)",
        "ok": r"perfume|wellness|fitness|self-care|star map|story book|mug|notebook|journal|herbal tea|"
              r"chocolate|gift card|cargo|jeans|pants",
    },
    "Mother's Day": {
        "core": rf"{FLOWERS}|{WELLNESS}|{JEWELLERY}|saree|kurti|kashmiri|perfume|candle",
        "ok": r"chocolate|star map|story book|letters|plant|decor|gift card|watch|mug|soap|gretting",
    },
    "Baby Shower": {
        "core": r"baby|teddy|plush|soft toy",
        "ok": r"toy|xylophone|guitar|drum|gift card|story book",
    },
    "Graduation": {
        "core": r"\bpens?\b|watch|notebook|journal|gift card",
        "ok": r"star map|story book|perfume|bracelet|wellness|self-care|fitness|shirt|office|mug|chocolate|bag",
    },
    "Housewarming": {
        "core": r"housewarming|plant|planter|decor|décor|candle|bamboo|recycled|upcycled",
        "ok": r"gift sets|mug|herbal tea|gift card|flower|lil|tulip|marigold",
    },
}


# Extra intents used only by the natural-language evaluation (scripts/compare_llm.py).
EXTRA_JUDGMENTS: dict[str, dict[str, str]] = {
    "Kids": {
        "core": KIDS,
        "ok": r"story book|gift card|chocolate|keychain",
    },
    "Retirement": {
        "core": rf"watch|{WELLNESS}|\bpens?\b",
        "ok": r"plant|decor|journal|notebook|gift card|perfume|star map|herbal tea|candle",
    },
    "Teacher": {
        "core": r"\bpens?\b|notebook|journal|plant|planter",
        "ok": rf"{FLOWERS}|chocolate|gift card|candle|mug|decor",
    },
    "Christmas": {
        "core": r"christmas|candle|chocolate|gift sets",
        "ok": r"gift card|snacks|teddy|plush|toy|decor|plant|herbal tea",
    },
    "Eco Wellness": {
        "core": rf"bamboo|recycled|upcycled|organic|plant|{WELLNESS}|herbal tea",
        "ok": r"candle|decor|journal|notebook|bath",
    },
}


def grade(occasion: str, title: str) -> int:
    lowered = title.lower()
    for word, owner in OCCASION_TITLE_WORDS.items():
        if word in lowered and owner != occasion:
            return 0
    if ADD_ONS.search(lowered):
        return 0
    rules = JUDGMENTS.get(occasion) or EXTRA_JUDGMENTS[occasion]
    if re.search(rules["core"], lowered):
        return 2
    if re.search(rules["ok"], lowered):
        return 1
    return 0
