"""Occasion understanding.

Turns free-text user input into an :class:`OccasionIntent`:

1. **Budget parsing** - "under ₹1,000", "below 500", "between 500 and 1500".
2. **Alias matching** - exact or phrase match against occasion aliases and
   recipient cues ("girlfriend" -> romantic, "child" -> kids).
3. **Fuzzy matching** - tolerates typos ("aniversary", "diwaali").
4. **Semantic matching** - an unfamiliar occasion ("Eid al-Fitr celebration",
   "farewell") is embedded and compared with every profile description; a
   close profile lends its concepts with a reduced weight.
5. Otherwise the raw query alone drives retrieval.

The occasion library is plain data (``CONCEPTS`` / ``OCCASIONS``): add an
occasion by appending one ``OccasionProfile``.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from app.services.preprocessing import fold, stem, tokenize


@dataclass(frozen=True)
class Concept:
    key: str
    phrase: str  # human-readable phrase used in explanations
    keywords: tuple[str, ...]  # stemmed tokens matched against product text


def _c(key: str, phrase: str, words: str) -> Concept:
    return Concept(key, phrase, tuple(stem(w) for w in words.split()))


CONCEPTS: dict[str, Concept] = {c.key: c for c in [
    _c("romance", "romance and love", "romantic romance love couple couples heart sensual intimate together forever"),
    _c("flowers", "flowers", "flower flowers bouquet rose roses lily lilies tulip tulips marigold bloom blooms blossom petal petals floral"),
    _c("chocolates", "chocolates and sweet treats", "chocolate chocolates cocoa treat treats sweet snack snacks indulgence"),
    _c("fragrance", "fragrance", "perfume perfumes fragrance scent parfum aroma"),
    _c("candles", "candles and ambience", "candle candles atmosphere ambience"),
    _c("jewellery", "jewellery", "necklace nacklace bracelet bracelets earring earrings earings jewel jewellery jewelry choker pearl studs"),
    _c("watches", "watches", "watch watches"),
    _c("personalised", "personalised keepsakes", "personalized personalised custom keepsake memory remembered memorable cherished"),
    _c("festive", "festive celebration", "festival festive festivity celebrate celebration tradition traditional prosperity"),
    _c("diwali", "Diwali", "diwali deepavali"),
    _c("holi", "Holi", "holi colors colours"),
    _c("christmas", "Christmas", "christmas holiday xmas"),
    _c("hampers", "gift hampers", "hamper hampers dry fruits nuts"),
    _c("celebration", "celebrations", "celebration celebrate celebrations party milestone milestones occasion birthday"),
    _c("kids", "gifts for children", "kid kids child children toy toys play playtime plush plushies teddy imagination learning cuddly"),
    _c("music_toys", "musical play", "music musical rhythm drum drums guitar guitars xylophone beats"),
    _c("crafts", "creative activities", "craft crafts diy slime painting coloring creative art"),
    _c("corporate", "office and corporate gifting", "corporate office work workday employee employees professional workplace executive"),
    _c("stationery", "stationery", "pen pens notebook notebooks journal journals writing"),
    _c("wellness", "wellness and self-care", "wellness self care calm relax relaxation balance health fitness skincare bath tea teas soothing"),
    _c("home", "home and decor", "home decor plant plants planter planters space spaces living warmth"),
    _c("new_home", "new beginnings at home", "housewarming new beginnings home"),
    _c("baby", "baby and newborn", "baby newborn shower precious first moments"),
    _c("wedding", "weddings and engagements", "wedding weddings engagement commitment marriage journey"),
    _c("ethnic_wear", "traditional attire", "saree sarees kurti kurtis suit suits attire heritage ethnic kashmiri"),
    _c("apparel", "apparel", "shirt shirts tshirt tshirts polo jeans pants cargos wear"),
    _c("gift_accessories", "gift presentation", "wrapping wrap box boxes ribbon ribbons seal seals greeting presentation"),
    _c("gift_cards", "gift cards", "card cards voucher"),
    _c("eco", "sustainable living", "sustainable eco recycled upcycled natural organic bamboo"),
    _c("long_distance", "staying connected", "distance missing letters connected apart"),
]}


@dataclass(frozen=True)
class OccasionProfile:
    name: str
    aliases: tuple[str, ...]
    description: str  # natural-language expansion used for embeddings
    concepts: dict[str, float]  # concept key -> weight in (0, 1]
    is_occasion: bool = True  # False for recipient/intent cues (not shown as chips)


OCCASIONS: list[OccasionProfile] = [
    OccasionProfile(
        "Valentine's Day",
        ("valentine", "valentines", "valentines day", "valentine day", "v day", "vday", "14 february"),
        "Romantic Valentine's Day gift for a partner, girlfriend or boyfriend: love and couple gifts, "
        "roses and flowers, chocolates, perfume, jewellery and personalised keepsakes.",
        {"romance": 1.0, "flowers": 0.8, "chocolates": 0.7, "fragrance": 0.6, "jewellery": 0.6,
         "personalised": 0.6, "candles": 0.4, "long_distance": 0.4},
    ),
    OccasionProfile(
        "Anniversary",
        ("anniversary", "wedding anniversary", "anniversery", "aniversary"),
        "Anniversary gift celebrating love and years together: romantic keepsakes, personalised gifts, "
        "jewellery, watches, flowers and fragrance for a spouse or partner.",
        {"romance": 1.0, "personalised": 0.8, "jewellery": 0.7, "flowers": 0.6, "watches": 0.5,
         "fragrance": 0.5, "wedding": 0.4},
    ),
    OccasionProfile(
        "Birthday",
        ("birthday", "bday", "b day", "birthday party", "happy birthday", "birth day"),
        "Birthday present to celebrate someone special: chocolates, flowers, personalised gifts, "
        "perfume, watches, jewellery, toys for kids, gift cards and nicely wrapped surprises.",
        {"celebration": 0.8, "chocolates": 0.6, "flowers": 0.6, "personalised": 0.6, "gift_cards": 0.5,
         "fragrance": 0.4, "watches": 0.4, "jewellery": 0.4, "kids": 0.3, "gift_accessories": 0.3},
    ),
    OccasionProfile(
        "Wedding",
        ("wedding", "marriage", "shaadi", "wedding gift", "reception"),
        "Wedding gift for the bride, groom or newly married couple: elegant jewellery, traditional "
        "ethnic attire, luxury gift hampers, home decor and personalised couple keepsakes.",
        {"wedding": 1.0, "jewellery": 0.7, "romance": 0.6, "hampers": 0.6, "ethnic_wear": 0.6,
         "personalised": 0.5, "home": 0.5, "celebration": 0.5},
    ),
    OccasionProfile(
        "Engagement",
        ("engagement", "ring ceremony", "roka", "proposal"),
        "Engagement gift celebrating a couple's commitment: romantic keepsakes, jewellery, "
        "personalised gifts and luxury hampers.",
        {"wedding": 1.0, "romance": 0.8, "jewellery": 0.8, "personalised": 0.5, "hampers": 0.4},
    ),
    OccasionProfile(
        "Diwali",
        ("diwali", "deepavali", "divali", "dipawali", "festival of lights"),
        "Diwali festival of lights gifts for family and friends: festive dry fruit hampers, sweets "
        "and chocolates, candles and decorative home items, traditional attire and jewellery.",
        {"diwali": 1.0, "festive": 0.8, "hampers": 0.9, "chocolates": 0.6, "candles": 0.6,
         "home": 0.4, "ethnic_wear": 0.5, "jewellery": 0.4},
    ),
    OccasionProfile(
        "Holi",
        ("holi", "festival of colours", "festival of colors"),
        "Holi festival of colours gifts: festive dry fruit hampers, sweets and treats to share with "
        "family and friends.",
        {"holi": 1.0, "festive": 0.8, "hampers": 0.8, "chocolates": 0.5},
    ),
    OccasionProfile(
        "Christmas",
        ("christmas", "xmas", "x mas", "christmas eve", "secret santa", "santa"),
        "Christmas holiday season gifts: festive hampers, chocolates, scented candles, cosy treats, "
        "toys for children and gift cards.",
        {"christmas": 1.0, "festive": 0.7, "hampers": 0.8, "chocolates": 0.6, "candles": 0.6,
         "kids": 0.4, "gift_cards": 0.4},
    ),
    OccasionProfile(
        "Office Party",
        ("office party", "office", "corporate", "corporate gift", "colleague", "coworker", "co worker",
         "boss", "employee", "team", "client", "work anniversary", "farewell"),
        "Corporate and office gifting for colleagues, employees or clients: premium pens and "
        "stationery, wellness kits, watches, gift cards and shareable hampers.",
        {"corporate": 1.0, "stationery": 0.7, "wellness": 0.6, "gift_cards": 0.6, "watches": 0.5,
         "hampers": 0.5, "chocolates": 0.4},
    ),
    OccasionProfile(
        "Mother's Day",
        ("mothers day", "mother day", "mother", "mom", "mum", "mummy", "maa"),
        "Mother's Day gift to pamper mom: flowers, wellness and self-care, skincare, fragrance, "
        "jewellery, candles and personalised keepsakes.",
        {"flowers": 0.8, "wellness": 0.8, "jewellery": 0.6, "fragrance": 0.6, "personalised": 0.6,
         "candles": 0.5, "ethnic_wear": 0.4},
    ),
    OccasionProfile(
        "Father's Day",
        ("fathers day", "father day", "father", "dad", "papa", "daddy"),
        "Father's Day gift for dad: classic watches, executive pens, shirts, fragrance, wellness "
        "and personalised keepsakes.",
        {"watches": 0.8, "stationery": 0.6, "apparel": 0.5, "personalised": 0.5, "fragrance": 0.4,
         "wellness": 0.4},
    ),
    OccasionProfile(
        "Baby Shower",
        ("baby shower", "newborn", "new born", "new baby", "godh bharai", "naming ceremony"),
        "Baby shower and newborn gifts: gentle keepsakes, soft toys, teddy bears and plushies for "
        "the baby, and celebration gifts for the parents.",
        {"baby": 1.0, "kids": 0.8, "celebration": 0.5, "personalised": 0.4},
    ),
    OccasionProfile(
        "Graduation",
        ("graduation", "convocation", "graduate", "passing out", "farewell party", "new job"),
        "Graduation gift celebrating an achievement and a new professional chapter: watches, "
        "premium pens, journals, personalised keepsakes and gift cards.",
        {"celebration": 0.6, "stationery": 0.8, "watches": 0.7, "personalised": 0.6,
         "gift_cards": 0.5, "corporate": 0.3},
    ),
    OccasionProfile(
        "Housewarming",
        ("housewarming", "house warming", "griha pravesh", "new home", "new house", "home warming"),
        "Housewarming gift for a new home: home decor, indoor plants and planters, scented candles, "
        "sustainable living items and hampers.",
        {"new_home": 1.0, "home": 0.9, "candles": 0.7, "eco": 0.5, "hampers": 0.5},
    ),
    OccasionProfile(
        "Raksha Bandhan",
        ("raksha bandhan", "rakhi", "rakshabandhan", "bhai dooj"),
        "Raksha Bandhan gift between brothers and sisters: chocolates, festive hampers, bracelets "
        "and jewellery, watches and gift cards.",
        {"festive": 0.7, "chocolates": 0.7, "hampers": 0.7, "jewellery": 0.5, "watches": 0.5,
         "gift_cards": 0.4},
    ),
    OccasionProfile(
        "Eid",
        ("eid", "eid mubarak", "eid ul fitr", "eid al fitr", "ramadan", "ramzan"),
        "Eid festive gifts: dry fruit hampers, sweets and chocolates, fragrance and attar, "
        "traditional attire.",
        {"festive": 0.8, "hampers": 0.9, "chocolates": 0.6, "fragrance": 0.6, "ethnic_wear": 0.6},
    ),
    OccasionProfile(
        "New Year",
        ("new year", "new years", "new years eve", "nye"),
        "New Year celebration gifts: hampers, chocolates, wellness kits, journals for fresh "
        "starts and gift cards.",
        {"celebration": 0.8, "hampers": 0.7, "chocolates": 0.6, "stationery": 0.5, "wellness": 0.5,
         "gift_cards": 0.5},
    ),
    OccasionProfile(
        "Friendship Day",
        ("friendship day", "friend", "friends", "best friend", "bestie", "bff"),
        "Gift for a friend: fun personalised keepsakes, bracelets, mugs, chocolates and treats.",
        {"personalised": 0.7, "chocolates": 0.7, "jewellery": 0.5, "celebration": 0.4},
    ),
    OccasionProfile(
        "Teacher's Day",
        ("teachers day", "teacher day", "teacher", "mentor", "professor"),
        "Thank-you gift for a teacher or mentor: pens, journals and notebooks, flowers, plants and "
        "chocolates.",
        {"stationery": 0.9, "flowers": 0.6, "home": 0.4, "chocolates": 0.5, "personalised": 0.4},
    ),
    OccasionProfile(
        "Retirement",
        ("retirement", "retiring", "retired", "superannuation"),
        "Retirement gift honouring a career and a relaxed new chapter: classic watches, wellness "
        "and self-care, home decor and plants, personalised keepsakes.",
        {"watches": 0.8, "wellness": 0.7, "home": 0.6, "personalised": 0.6, "corporate": 0.3},
    ),
    OccasionProfile(
        "Thank You",
        ("thank you", "thanks", "thankyou", "appreciation", "gratitude"),
        "Gift to say thank you: flowers, chocolates, hampers and gift cards.",
        {"flowers": 0.7, "chocolates": 0.7, "hampers": 0.6, "gift_cards": 0.6},
    ),
    # --- recipient / intent cues: merged with any detected occasion ---------
    OccasionProfile(
        "Romantic",
        ("romantic", "romance", "girlfriend", "boyfriend", "wife", "husband", "partner", "fiance",
         "fiancee", "spouse", "my love", "date night", "long distance"),
        "Romantic gift for a partner: love and couple gifts, roses, chocolates, perfume, jewellery "
        "and personalised keepsakes.",
        {"romance": 1.0, "flowers": 0.7, "chocolates": 0.6, "fragrance": 0.6, "jewellery": 0.6,
         "personalised": 0.6, "long_distance": 0.5},
        is_occasion=False,
    ),
    OccasionProfile(
        "Kids",
        ("kid", "kids", "child", "children", "son", "daughter", "toddler", "nephew", "niece", "boy",
         "girl", "children's day", "childrens day", "kids party"),
        "Gift for a child: fun toys, soft plushies and teddy bears, musical toys, DIY craft and "
        "colouring kits.",
        {"kids": 1.0, "music_toys": 0.7, "crafts": 0.7},
        is_occasion=False,
    ),
    OccasionProfile(
        "Eco-conscious",
        ("eco friendly", "eco", "sustainable", "green", "environment", "organic", "nature lover"),
        "Sustainable eco-friendly gift: recycled and upcycled products, bamboo, plants and organic "
        "self-care.",
        {"eco": 1.0, "home": 0.5, "wellness": 0.5},
        is_occasion=False,
    ),
]

# Query-term synonyms used by the keyword signal (applied after stemming).
KEYWORD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "child": ("kid",), "children": ("kid",), "kid": ("child",), "toddler": ("kid",),
    "girlfriend": ("romantic", "love"), "boyfriend": ("romantic", "love"),
    "wife": ("romantic", "love"), "husband": ("romantic", "love"), "partner": ("couple",),
    "mom": ("mother",), "mum": ("mother",), "dad": ("father",),
    "xma": ("christmas",), "xmas": ("christmas",), "deepavali": ("diwali",), "divali": ("diwali",),
    "jewelry": ("jewellery",), "perfume": ("fragrance",), "scent": ("perfume",),
    "office": ("corporate",), "corporate": ("office",), "colleague": ("corporate", "office"),
    "newborn": ("baby",), "housewarming": ("home",), "chocolate": ("cocoa",),
}


@dataclass
class OccasionIntent:
    raw_query: str
    search_text: str  # query with budget phrases removed
    keyword_terms: list[str]
    concept_weights: dict[str, float] = field(default_factory=dict)
    matched_profiles: list[OccasionProfile] = field(default_factory=list)
    match_type: str = "none"  # exact | phrase | fuzzy | semantic | none | generic
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    # Set only by the optional LLM layer: a label for occasions outside the
    # profile library, and theme/preference text added to the query embedding.
    display_override: Optional[str] = None
    extra_expansion: str = ""

    @property
    def display_name(self) -> Optional[str]:
        if self.display_override:
            return self.display_override
        occasions = [p.name for p in self.matched_profiles if p.is_occasion]
        names = occasions or [p.name for p in self.matched_profiles]
        return " + ".join(names) if names else None

    @property
    def expansion_text(self) -> str:
        parts = [p.description for p in self.matched_profiles]
        if self.extra_expansion:
            parts.append(self.extra_expansion)
        return " ".join(parts)

    @property
    def concepts(self) -> list[Concept]:
        return [CONCEPTS[k] for k in sorted(self.concept_weights, key=self.concept_weights.get, reverse=True)]


# --------------------------------------------------------------------------- #
# Budget parsing
# --------------------------------------------------------------------------- #
# "(?![a-z])" keeps the k suffix from eating the start of a word ("under 5 kids").
_NUM = r"(?:rs\.?|inr|₹)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k(?![a-z]))?\s*(?:rs\b|rupees|inr|/-)?"
_BETWEEN = re.compile(rf"\bbetween\s+{_NUM}\s*(?:and|to|-)\s*{_NUM}", re.I)
# "500 to 1000", "from ₹500 - ₹1000", "1k-2k"
_RANGE = re.compile(rf"(?:\bfrom\s+)?(?<![\w.]){_NUM}\s*(?:to|-|–)\s*{_NUM}", re.I)
# Negated lower bounds ("nothing above 1500", "no more than 2k") are upper bounds;
# they are listed first so the _MIN pattern below never sees them.
_MAX = re.compile(
    rf"(?:\b(?:(?:nothing|not|no)\s+(?:above|over|more than|beyond|exceeding)|not exceeding|at most|"
    rf"under|below|less than|upto|up to|within|max|maximum|cheaper than)\s+"
    rf"|\bbudget\b(?:\s+(?:of|is))?\s*[:=]?\s*){_NUM}",
    re.I,
)
_MIN = re.compile(rf"(?:\b(?:above|over|more than|min|minimum|at least|starting)\s+){_NUM}", re.I)
# A lone amount with a currency marker ("₹2000 gift", "2000 rupees") is a budget cap.
_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹)\s*(\d[\d,]*(?:\.\d+)?)\s*(k(?![a-z]))?|(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(k)?\s*(?:rs\b|rupees|inr|/-)",
    re.I,
)
_CURRENCY = re.compile(r"rs\b|inr|₹|rupee|/-", re.I)
# "5 year old", "6 yrs", "18 months": ages, never prices.
_AGE_AFTER = re.compile(r"\s*-?\s*(?:years?|yrs?|y/?o|months?|old)\b", re.I)
_APPROX_BEFORE = re.compile(r"\b(?:around|about|approx\w*|roughly)\s*$|~\s*$", re.I)
# Bare numbers below this, without a currency marker or "k", are ages or counts
# ("toys for kids under 5", "over 18"); the cheapest catalog item costs more.
MIN_UNMARKED_AMOUNT = 50


def _to_amount(number: str, k_suffix: Optional[str]) -> float:
    value = float(number.replace(",", ""))
    return value * 1000 if k_suffix else value


def _amounts(match: re.Match) -> list[float]:
    groups = match.groups()
    return [_to_amount(groups[i], groups[i + 1]) for i in range(0, len(groups), 2) if groups[i]]


def _find_price(pattern: re.Pattern, text: str) -> Optional[re.Match]:
    """First match of ``pattern`` that reads as a price rather than an age or count."""
    for match in pattern.finditer(text):
        if _AGE_AFTER.match(text, match.end()):
            continue
        marked = bool(_CURRENCY.search(match.group(0))) or any(
            match.group(i) for i in range(2, len(match.groups()) + 1, 2))
        if marked or min(_amounts(match)) >= MIN_UNMARKED_AMOUNT:
            return match
    return None


def parse_budget(text: str) -> tuple[str, Optional[float], Optional[float]]:
    """Extract (text_without_budget, min_price, max_price)."""
    min_price = max_price = None

    def cut(match: re.Match) -> str:
        return text[: match.start()] + " " + text[match.end():]

    match = _find_price(_BETWEEN, text) or _find_price(_RANGE, text)
    if match:
        low, low_k, high, high_k = match.groups()
        # "1-2k" shares one suffix (₹1,000-2,000); "500 to 2k" does not.
        shared_k = high_k if not low_k and _to_amount(low, None) < _to_amount(high, None) else low_k
        min_price, max_price = _to_amount(low, shared_k), _to_amount(high, high_k)
        text = cut(match)
    match = _find_price(_MAX, text)
    if match:
        max_price = _amounts(match)[0]
        text = cut(match)
    match = _find_price(_MIN, text)
    if match:
        min_price = _amounts(match)[0]
        text = cut(match)
    if min_price is None and max_price is None:
        match = _find_price(_AMOUNT, text)
        # "around ₹1000" is not a hard cap; leave it in the text for the other signals.
        if match and not _APPROX_BEFORE.search(text[: match.start()]):
            max_price = _amounts(match)[0]
            text = cut(match)
    if min_price is not None and max_price is not None and min_price > max_price:
        min_price, max_price = max_price, min_price
    return " ".join(text.split()), min_price, max_price


# --------------------------------------------------------------------------- #
# Occasion matching
# --------------------------------------------------------------------------- #
# "5 year old", "5-7 yrs old", "8yo", "18 months old"; "10 year anniversary" is not an age.
_AGE = re.compile(
    r"\b(\d{1,2})\s*(?:(?:-|to)\s*\d{1,2}\s*)?-?\s*(?:(years?|yrs?|months?)\s*-?\s*old\b|(y/?o)\b)", re.I)
MAX_CHILD_AGE = 12


def _is_child_age(text: str) -> bool:
    return any((m.group(2) or "").lower().startswith("month") or int(m.group(1)) <= MAX_CHILD_AGE
               for m in _AGE.finditer(text))


def normalize_phrase(text: str) -> str:
    text = fold(text).replace("'", "").replace("’", "")
    return " ".join(re.findall(r"[a-z0-9]+", text))


class OccasionService:
    """Matches queries to occasion profiles.

    ``encode`` is an optional function mapping texts to L2-normalised vectors;
    when provided it enables semantic matching of unfamiliar occasions.
    """

    SEMANTIC_MATCH_THRESHOLD = 0.55
    SEMANTIC_WEIGHT_SCALE = 0.6  # borrowed concepts count less than explicit ones

    def __init__(self, profiles: Optional[list[OccasionProfile]] = None,
                 encode: Optional[Callable[[list[str]], np.ndarray]] = None,
                 semantic_threshold: Optional[float] = None) -> None:
        self.profiles = profiles or OCCASIONS
        self._alias_index: dict[str, OccasionProfile] = {}
        for profile in self.profiles:
            for alias in (profile.name, *profile.aliases):
                self._alias_index[normalize_phrase(alias)] = profile
        self._aliases_by_length = sorted(self._alias_index, key=len, reverse=True)
        self._encode = encode
        self._profile_vectors: Optional[np.ndarray] = None
        if semantic_threshold is not None:
            self.SEMANTIC_MATCH_THRESHOLD = semantic_threshold
        if encode is not None:
            self._profile_vectors = encode(
                [f"{p.name}. {p.description}" for p in self.profiles if p.is_occasion]
            )

    @property
    def occasion_names(self) -> list[str]:
        return [p.name for p in self.profiles if p.is_occasion]

    def _phrase_matches(self, phrase: str) -> list[OccasionProfile]:
        """Longest-first alias matching on word boundaries."""
        matched: list[OccasionProfile] = []
        remaining = f" {phrase} "
        for alias in self._aliases_by_length:
            needle = f" {alias} "
            if needle in remaining:
                profile = self._alias_index[alias]
                if profile not in matched:
                    matched.append(profile)
                remaining = remaining.replace(needle, " ")
        return matched

    def match_aliases(self, text: str) -> list[OccasionProfile]:
        """Profiles whose aliases appear verbatim (word-bounded) in ``text``."""
        return self._phrase_matches(normalize_phrase(text))

    def _fuzzy_matches(self, phrase: str) -> list[OccasionProfile]:
        matched: list[OccasionProfile] = []
        close = difflib.get_close_matches(phrase, self._alias_index.keys(), n=1, cutoff=0.82)
        if close:
            return [self._alias_index[close[0]]]
        single_word_aliases = [a for a in self._alias_index if " " not in a and len(a) >= 4]
        for token in phrase.split():
            if len(token) < 4:
                continue
            close = difflib.get_close_matches(token, single_word_aliases, n=1, cutoff=0.8)
            if close and self._alias_index[close[0]] not in matched:
                matched.append(self._alias_index[close[0]])
        return matched

    def _semantic_matches(self, text: str) -> list[OccasionProfile]:
        if self._encode is None or self._profile_vectors is None or not text:
            return []
        query = self._encode([text])[0]
        sims = self._profile_vectors @ query
        best = int(np.argmax(sims))
        if float(sims[best]) < self.SEMANTIC_MATCH_THRESHOLD:
            return []
        return [[p for p in self.profiles if p.is_occasion][best]]

    def understand(self, query: str) -> OccasionIntent:
        search_text, min_price, max_price = parse_budget(query)
        phrase = normalize_phrase(search_text)

        if phrase in self._alias_index:
            profiles, match_type = [self._alias_index[phrase]], "exact"
        elif profiles := self._phrase_matches(phrase):
            match_type = "phrase"
        elif profiles := self._fuzzy_matches(phrase):
            match_type = "fuzzy"
        elif profiles := self._semantic_matches(search_text):
            match_type = "semantic"
        else:
            profiles, match_type = [], "none"
        # A child's age ("5 year old", "18 months") is a Kids cue even without a kid word.
        kids = self._alias_index.get("kids")
        if kids and kids not in profiles and _is_child_age(search_text):
            profiles = [*profiles, kids]
            match_type = "phrase" if match_type in {"none", "semantic"} else match_type

        scale = self.SEMANTIC_WEIGHT_SCALE if match_type == "semantic" else 1.0
        weights: dict[str, float] = {}
        for profile in profiles:
            for key, weight in profile.concepts.items():
                weights[key] = max(weights.get(key, 0.0), weight * scale)

        terms = tokenize(search_text)
        expanded = list(dict.fromkeys(terms + [s for t in terms for s in KEYWORD_SYNONYMS.get(t, ())]))
        if not terms and not profiles:
            match_type = "generic"  # e.g. "something under 1000": rank by general giftability

        return OccasionIntent(
            raw_query=query,
            search_text=search_text,
            keyword_terms=expanded,
            concept_weights=weights,
            matched_profiles=profiles,
            match_type=match_type,
            min_price=min_price,
            max_price=max_price,
        )
