"""Regression tests for the Coach restaurant-lookup allergen safety net.

Repro this closes: an athlete with a real shellfish allergy on file asked
for options at Red Lobster. The prompt correctly told the model "NEVER
suggest items containing shellfish" — the model ignored it and recommended
Lobster Tail and Garlic Parmesan Shrimp anyway. The prompt rule alone was a
soft check; find_allergen_violations + the regenerate/fallback logic in
_answer_with_restaurant / _answer_with_nearby_restaurants is the hard check
behind it.
"""
import os
os.environ["DB_PATH"] = ":memory:"

from api.services.safety_filters import find_allergen_violations
from api.services.knowledge.answer import (
    _scan_categories,
    _answer_with_restaurant,
    _answer_with_nearby_restaurants,
)
from api.services.knowledge.web_search import RestaurantSearchResult


# ── find_allergen_violations (safety_filters.py) ──────────────────────────────

def test_finds_shellfish_in_real_repro_text():
    text = (
        "I can definitely help with that! Red Lobster has a few meal options "
        "that can work well for Kabir's fueling needs. Their Lobster Tail or "
        "Garlic Parmesan Shrimp (with a side of rice) can be great for "
        "post-game recovery. If he's looking for something lighter, their "
        "Salmon or Grilled Shrimp Salad could be a good pre-game option."
    )
    assert set(find_allergen_violations(text, ["shellfish"])) == {"shellfish"}


def test_safe_text_has_no_violations():
    text = "The grilled chicken breast with steamed veggies is a solid post-game pick."
    assert find_allergen_violations(text, ["shellfish", "dairy"]) == []


def test_no_categories_means_no_scan():
    text = "Lobster tail and shrimp scampi for everyone."
    assert find_allergen_violations(text, []) == []


def test_word_boundary_avoids_false_positive():
    # "eggplant" must not trip the "egg" keyword.
    text = "Try the grilled eggplant parmesan-free veggie plate."
    assert "egg" not in find_allergen_violations(text, ["egg"])


# ── _scan_categories (answer.py) — allergies + intolerances → categories ─────

def test_scan_categories_normalizes_allergy_synonyms():
    assert _scan_categories(["shrimp", "peanuts"], []) == ["shellfish", "peanut"]


def test_scan_categories_handles_dietary_intolerance_phrasing():
    assert _scan_categories([], ["dairy-free"]) == ["dairy"]
    assert _scan_categories([], ["lactose intolerant"]) == ["dairy"]
    assert _scan_categories([], ["Gluten Free"]) == ["gluten"]


def test_scan_categories_combines_and_dedupes():
    result = _scan_categories(["shellfish"], ["shellfish-free"])
    assert result == ["shellfish"]


def test_scan_categories_empty_when_nothing_on_file():
    assert _scan_categories([], []) == []


# ── _answer_with_restaurant integration: the actual reported bug ─────────────

def _menu_result():
    return RestaurantSearchResult(
        url="https://redlobster.com/menu",
        title="Red Lobster Menu",
        snippet="",
        content="Lobster Tail, Garlic Parmesan Shrimp, Grilled Chicken, Salmon, Grilled Shrimp Salad",
    )


def test_unsafe_first_draft_is_regenerated_and_scrubbed(monkeypatch):
    """First model draft violates the allergy; the retry comes back clean —
    the clean retry text must be what's shown to the user."""
    import api.services.knowledge.answer as answer_mod

    monkeypatch.setattr(answer_mod, "is_configured", lambda: True)
    monkeypatch.setattr("api.services.knowledge.web_search.search_restaurant_menu", lambda *a, **k: [_menu_result()])

    calls = {"n": 0}

    def fake_converse(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return "Try the Lobster Tail or Garlic Parmesan Shrimp for recovery."
        return "Try the grilled chicken breast with a side of rice for recovery."

    monkeypatch.setattr(answer_mod, "converse_text", fake_converse)

    athlete = {"id": 71, "first_name": "Kabir", "allergies": "shellfish,soy", "dietary_restrictions": None}
    result = _answer_with_restaurant("healthy options for red lobster", athlete, "Red Lobster")

    assert calls["n"] == 2, "should have retried once after the first draft violated the allergy"
    # "Red Lobster" as the venue name in the deterministic header is expected
    # and fine — what must never appear is an actual shellfish dish.
    assert "lobster tail" not in result["answer"].lower()
    assert "shrimp" not in result["answer"].lower()
    assert "grilled chicken" in result["answer"].lower()


def test_unsafe_after_retry_falls_back_to_safe_message_not_the_bad_text(monkeypatch):
    """If even the retry still names the allergen, never leak model text —
    return the fixed safe fallback instead."""
    import api.services.knowledge.answer as answer_mod

    monkeypatch.setattr(answer_mod, "is_configured", lambda: True)
    monkeypatch.setattr("api.services.knowledge.web_search.search_restaurant_menu", lambda *a, **k: [_menu_result()])
    monkeypatch.setattr(answer_mod, "converse_text", lambda **k: "The Garlic Parmesan Shrimp is a great pick.")

    athlete = {"id": 71, "first_name": "Kabir", "allergies": "shellfish", "dietary_restrictions": None}
    result = _answer_with_restaurant("healthy options for red lobster", athlete, "Red Lobster")

    assert "shrimp" not in result["answer"].lower()
    assert "couldn't find options" in result["answer"].lower()


def test_safe_first_draft_is_never_regenerated(monkeypatch):
    """A clean first draft should not trigger a second model call at all."""
    import api.services.knowledge.answer as answer_mod

    monkeypatch.setattr(answer_mod, "is_configured", lambda: True)
    monkeypatch.setattr("api.services.knowledge.web_search.search_restaurant_menu", lambda *a, **k: [_menu_result()])

    calls = {"n": 0}

    def fake_converse(**kwargs):
        calls["n"] += 1
        return "The grilled chicken breast with rice is a solid pick."

    monkeypatch.setattr(answer_mod, "converse_text", fake_converse)

    athlete = {"id": 71, "first_name": "Kabir", "allergies": "shellfish", "dietary_restrictions": None}
    _answer_with_restaurant("healthy options for red lobster", athlete, "Red Lobster")

    assert calls["n"] == 1


def test_athlete_with_no_allergies_gets_no_safety_gate_at_all(monkeypatch):
    """No allergies/restrictions on file → scan_cats is empty → the shellfish-
    heavy draft is never blocked, since there's nothing to protect against."""
    import api.services.knowledge.answer as answer_mod

    monkeypatch.setattr(answer_mod, "is_configured", lambda: True)
    monkeypatch.setattr("api.services.knowledge.web_search.search_restaurant_menu", lambda *a, **k: [_menu_result()])

    calls = {"n": 0}

    def fake_converse(**kwargs):
        calls["n"] += 1
        return "Try the Lobster Tail or Garlic Parmesan Shrimp for recovery."

    monkeypatch.setattr(answer_mod, "converse_text", fake_converse)

    athlete = {"id": 99, "first_name": "Alex", "allergies": None, "dietary_restrictions": None}
    result = _answer_with_restaurant("healthy options for red lobster", athlete, "Red Lobster")

    assert calls["n"] == 1
    assert "lobster tail" in result["answer"].lower()


# ── _answer_with_nearby_restaurants: restaurant-name-level scan ──────────────

class _FakeCandidate:
    def __init__(self, name):
        self.name = name
        self.category = "Seafood"
        self.distance_m = 800.0
        self.rating = 4.5
        self.review_count = 200
        self.price_level = 2
        self.open_now = True
        self.address = "123 Main St"
        self.place_id = "abc123"
        self.maps_url = "https://maps.example.com/abc123"


def test_nearby_restaurants_scrubs_allergen_bearing_recommendation(monkeypatch):
    import api.services.knowledge.answer as answer_mod

    monkeypatch.setattr(answer_mod, "is_configured", lambda: True)
    monkeypatch.setattr(
        "api.services.places.nearby_search.search_nearby_restaurants",
        lambda *a, **k: [_FakeCandidate("Red Lobster")],
    )

    calls = {"n": 0}

    def fake_converse(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return "Red Lobster is a great nearby pick for seafood lovers."
        return "There's a solid grilled-chicken spot nearby for recovery."

    monkeypatch.setattr(answer_mod, "converse_text", fake_converse)

    athlete = {"id": 71, "first_name": "Kabir", "allergies": "shellfish", "dietary_restrictions": None}
    result = _answer_with_nearby_restaurants("restaurants near me", athlete, 37.0, -122.0)

    assert calls["n"] == 2
    assert "lobster" not in result["answer"].lower()
