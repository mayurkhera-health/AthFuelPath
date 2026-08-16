"""
Performance Plate — per-window plate shapes + food-option selection.

Two data tables, both RDN-editable:
  PLATE_TIMINGS   — the 5 plate *shapes* (canonical 4 sections: carbs/protein/
                    veg/fat), transcribed from the RDN prototype
                    (athfuelpath_performance_plate_v2_1.html). `pct` is plate AREA
                    (visual emphasis), NOT a gram ratio.
  WINDOW_TO_PLATE — maps each real fueling-window key → (shape, title, subtitle,
                    recipe profile). ⚠️ RDN-tunable; the shape/window pairing and
                    the reuse choices (lunch→balanced, rebuild→recovery) are
                    Phase-1 defaults pending Purvi sign-off.

Section grams are template values from the prototype — a first pass. They should
later be replaced with the athlete's real per-window macro targets so the plate
chip matches the window card. Flagged; not wired yet.
"""
import json
import os
import re


def performance_plate_enabled() -> bool:
    """Feature flag — ships dark. Flip PERFORMANCE_PLATE_ENABLED=true (Fly secret)
    only after RDN sign-off on allergen tags + the window→plate mapping."""
    return os.environ.get("PERFORMANCE_PLATE_ENABLED", "false").lower() == "true"


# Spec-locked palette (do not change — plate + dots share these).
COLORS = {"carbs": "#E8B84B", "protein": "#D96B4A", "veg": "#5FA83C", "fat": "#5B8FD9"}

# key -> {pct, grams} per canonical section. pct sums to 100 (plate area).
PLATE_TIMINGS = {
    "carb_forward_meal": {  # breakfast / pre-event meal ~3h before
        "carbs":   {"pct": 50, "grams": "60g"},
        "protein": {"pct": 25, "grams": "20g"},
        "veg":     {"pct": 15, "grams": ""},
        "fat":     {"pct": 10, "grams": "15g"},
    },
    "fast_carb_snack": {  # quick top-up ~1h before
        "carbs":   {"pct": 82, "grams": "30g"},
        "protein": {"pct": 12, "grams": "5g"},
        "veg":     {"pct": 0,  "grams": ""},
        "fat":     {"pct": 6,  "grams": ""},
    },
    "recovery": {  # within 30 min after training
        "carbs":   {"pct": 38, "grams": "40g"},
        "protein": {"pct": 35, "grams": "25g"},
        "veg":     {"pct": 17, "grams": ""},
        "fat":     {"pct": 10, "grams": "10g"},
    },
    "balanced_meal": {  # lunch / dinner
        "carbs":   {"pct": 40, "grams": "70g"},
        "protein": {"pct": 25, "grams": "28g"},
        "veg":     {"pct": 25, "grams": ""},
        "fat":     {"pct": 10, "grams": "20g"},
    },
    "protein_snack": {  # evening snack before bed
        "carbs":   {"pct": 35, "grams": "20g"},
        "protein": {"pct": 45, "grams": "15g"},
        "veg":     {"pct": 0,  "grams": ""},
        "fat":     {"pct": 20, "grams": "5g"},
    },
}

_LABELS = {"carbs": "Carbs", "protein": "Protein", "veg": "Veg", "fat": "Good fat"}

# window_key -> (timing shape, title, subtitle, recipe profile_key for recipe_db)
# Windows absent here (between_games, between_sessions, keep_going) get NO plate
# — they are nudge/hydration windows, not eating windows.
WINDOW_TO_PLATE = {
    "fuel_before":        ("carb_forward_meal", "Pre-game meal — ~3 hrs before", "More carbs · moderate protein · good fat · colorful veg", "pre_game"),
    "pre_event_meal":     ("carb_forward_meal", "Pre-game meal — ~3 hrs before", "More carbs · moderate protein · good fat · colorful veg", "pre_game"),
    "quick_snack":        ("fast_carb_snack",   "Quick top-up — ~1 hr before",   "Fast carbs · light protein · easy to digest",           "pre_game_snack"),
    "top_up_snack":       ("fast_carb_snack",   "Top-up — before your event",    "Fast carbs · light protein · easy to digest",           "pre_game_snack"),
    "fuel_after":         ("recovery",          "Recovery — within 30 min after","Equal carbs + protein · anti-inflammatory",             "post_game"),
    "fuel_after_primary": ("recovery",          "Recovery — within 30 min after","Equal carbs + protein · anti-inflammatory",             "post_game"),
    "fuel_after_second":  ("recovery",          "Recovery meal",                 "Rebuild with protein · steady carbs",                   "post_game"),
    "everyday_breakfast": ("carb_forward_meal", "Breakfast",                     "More carbs · moderate protein · good fat · colorful veg", "breakfast"),
    "everyday_lunch":     ("balanced_meal",     "Lunch",                         "Balanced plate · plenty of veg",                        "lunch"),
    "everyday_dinner":    ("balanced_meal",     "Dinner",                        "Balanced plate · plenty of veg",                        "dinner"),
    "everyday_snack":     ("protein_snack",     "Evening snack",                 "Protein-forward · light · easy on the stomach",         "snack"),
}

# ── Allergen normalization (athlete free-text → recipe big-9 vocabulary) ──────
# Recipes tag ONLY the FDA big-9. Athlete-entered synonyms map onto that vocab so
# the filter actually catches them. ⚠️ Non-big-9 allergies (e.g. "corn") cannot be
# filtered — recipes carry no tag for them. Surface that limitation to the RDN.
_ALLERGEN_SYNONYMS = {
    "milk": "dairy", "lactose": "dairy", "cheese": "dairy", "dairy": "dairy",
    "egg": "egg", "eggs": "egg",
    "fish": "fish",
    "shellfish": "shellfish", "shrimp": "shellfish", "crab": "shellfish",
    "lobster": "shellfish", "crustacean": "shellfish",
    "tree nut": "tree nuts", "tree nuts": "tree nuts", "nut": "tree nuts", "nuts": "tree nuts",
    "almond": "tree nuts", "walnut": "tree nuts", "cashew": "tree nuts",
    "pecan": "tree nuts", "pistachio": "tree nuts", "hazelnut": "tree nuts",
    "peanut": "peanut", "peanuts": "peanut",
    "gluten": "gluten", "wheat": "gluten", "gluten/wheat": "gluten",
    "soy": "soy", "soya": "soy", "soybean": "soy",
    "sesame": "sesame", "sesame seed": "sesame",
}


def parse_restrictions(raw) -> list[str]:
    """Athlete allergies/dietary may be a JSON-array string, a list, or CSV."""
    if not raw:
        return []
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                raw = json.loads(s)
            except Exception:
                raw = s.split(",")
        else:
            raw = s.split(",")
    out = []
    for item in raw:
        t = str(item).strip()
        if t and t.lower() != "none":
            out.append(t)
    return out


def normalize_allergens(terms: list[str]) -> list[str]:
    """Map athlete allergen terms onto the recipe big-9 vocabulary (safety filter)."""
    seen = []
    for t in terms:
        norm = _ALLERGEN_SYNONYMS.get(t.strip().lower(), t.strip().lower())
        if norm not in seen:
            seen.append(norm)
    return seen


def _resolve(window_key: str):
    """Match a window key, tolerating tournament/double-session numeric suffixes
    (fuel_after_primary_1, top_up_snack_2, between_games_1_2 → base key)."""
    if not window_key:
        return None
    entry = WINDOW_TO_PLATE.get(window_key)
    if entry:
        return entry
    return WINDOW_TO_PLATE.get(re.sub(r"(_\d+)+$", "", window_key))


def plate_for_window(window_key: str) -> dict | None:
    """Assemble the plate payload for a window, or None if the window gets no plate."""
    entry = _resolve(window_key)
    if not entry:
        return None
    shape_key, title, subtitle, _profile = entry
    shape = PLATE_TIMINGS[shape_key]
    sections = [
        {
            "key": k,
            "label": _LABELS[k],
            "pct": shape[k]["pct"],
            "grams": shape[k]["grams"],
            "color": COLORS[k],
        }
        for k in ("carbs", "protein", "veg", "fat")
        if shape[k]["pct"] > 0
    ]
    return {"title": title, "subtitle": subtitle, "sections": sections}


def recipe_profile_for_window(window_key: str) -> str | None:
    entry = _resolve(window_key)
    return entry[3] if entry else None


def select_options(recipes: list[dict], n: int = 5) -> list[dict]:
    """Pick up to n recipes with cuisine variety, as {id, short_label, plate_sections}.
    Deterministic (file order, distinct cuisines first) — stable across requests."""
    seen_cuisines: set[str] = set()
    primary, rest = [], []
    for r in recipes:
        cuisine = r.get("cuisine", "")
        if cuisine not in seen_cuisines:
            seen_cuisines.add(cuisine)
            primary.append(r)
        else:
            rest.append(r)
        if len(primary) >= n:
            break
    chosen = (primary + rest)[:n]
    return [
        {
            "id": r["id"],
            "short_label": r.get("short_label") or r["name"],
            "plate_sections": r.get("plate_sections", []),
        }
        for r in chosen
    ]
