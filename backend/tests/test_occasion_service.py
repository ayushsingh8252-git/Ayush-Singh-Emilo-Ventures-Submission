"""Occasion understanding: aliases, typos, intent cues, budgets."""

from __future__ import annotations

import pytest

from app.services.occasion_service import OccasionService, parse_budget

service = OccasionService()  # lexical matching only; semantic matching is tested via the engine


@pytest.mark.parametrize("query, expected", [
    ("Valentine's Day", "Valentine's Day"),
    ("valentines", "Valentine's Day"),
    ("DIWALI", "Diwali"),
    ("Deepavali", "Diwali"),
    ("xmas", "Christmas"),
    ("office party", "Office Party"),
    ("house warming", "Housewarming"),
    ("Mothers day", "Mother's Day"),
])
def test_aliases_and_spelling_variants(query, expected):
    assert service.understand(query).display_name == expected


@pytest.mark.parametrize("query, expected", [
    ("birthdy", "Birthday"),
    ("aniversry", "Anniversary"),
    ("graduaton", "Graduation"),
    ("weding", "Wedding"),
])
def test_typos_are_fuzzy_matched(query, expected):
    intent = service.understand(query)
    assert intent.display_name == expected
    assert intent.match_type == "fuzzy"


def test_recipient_cues_inside_free_text():
    assert service.understand("Something romantic for my girlfriend").display_name == "Romantic"
    assert service.understand("Gift for a child").display_name == "Kids"
    intent = service.understand("birthday gift for my son")
    assert {p.name for p in intent.matched_profiles} == {"Birthday", "Kids"}
    assert intent.display_name == "Birthday"  # real occasions take precedence over cues


def test_unknown_occasion_keeps_raw_query():
    intent = service.understand("quantum physics conference")
    assert intent.match_type == "none"
    assert intent.matched_profiles == []
    assert "quantum" in intent.keyword_terms


@pytest.mark.parametrize("text, expected", [
    ("Something under ₹1,000", (None, 1000.0)),
    ("birthday gift below 500", (None, 500.0)),
    ("under rs 2k", (None, 2000.0)),
    ("between 500 and 1500", (500.0, 1500.0)),
    ("above 3000 wedding", (3000.0, None)),
    ("mom's bday, nothing above 1500 rupees", (None, 1500.0)),
    ("not more than 2k", (None, 2000.0)),
    ("no more than ₹800 please", (None, 800.0)),
    ("at most 1200", (None, 1200.0)),
    ("not exceeding 2500", (None, 2500.0)),
    ("Diwali", (None, None)),
    # phrasings that used to be ignored
    ("my budget is 1500", (None, 1500.0)),
    ("budget: 2000", (None, 2000.0)),
    ("birthday gift 500 to 1000", (500.0, 1000.0)),
    ("from ₹500 - ₹1000", (500.0, 1000.0)),
    ("1-2k", (1000.0, 2000.0)),
    ("between 500 and 2k", (500.0, 2000.0)),
    ("₹2000 gift for mom", (None, 2000.0)),
    ("gift around 2000 rupees", (None, None)),  # approximate, not a hard cap
    # ages and counts are not prices
    ("toys for kids under 5", (None, None)),
    ("gift for a 5 to 7 year old", (None, None)),
    ("over 18 birthday gift", (None, None)),
    ("under 5 kids", (None, None)),
    ("teddy under 500 for my 2 yr old", (None, 500.0)),
])
def test_budget_parsing(text, expected):
    _, min_price, max_price = parse_budget(text)
    assert (min_price, max_price) == expected


def test_budget_phrase_is_removed_from_search_text():
    intent = service.understand("Diwali gift under ₹2,000")
    assert intent.max_price == 2000.0
    assert intent.display_name == "Diwali"
    assert "2" not in intent.search_text


@pytest.mark.parametrize("query, expected", [
    ("gift for a 5 to 7 year old", True),
    ("present for my 8yo", True),
    ("birthday gift for a 6 year old", True),
    ("10 year anniversary", False),
    ("gift for my 40 year old brother", False),
])
def test_child_age_is_a_kids_cue(query, expected):
    names = [p.name for p in service.understand(query).matched_profiles]
    assert ("Kids" in names) is expected


def test_budget_only_query_is_generic():
    intent = service.understand("Something under ₹1,000")
    assert intent.match_type == "generic"
