from datetime import date as _date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, model_validator
from api.models import RecipeSwapRequest, RecipeGenerateRequest
from api.services import recipe_db, claude_ai, recipe_generator
from api.services.recipe_db import PROFILE_TO_DB_CATEGORIES
from api.database import get_conn
from api.utils.week import get_week_start as _get_week_start
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "spice": [
        "salt", "pepper", "paprika", "cumin", "coriander", "turmeric",
        "cinnamon", "nutmeg", "oregano", "thyme", "rosemary", "basil",
        "bay leaf", "garlic powder", "onion powder", "chili powder",
        "cayenne", "red pepper flakes", "italian seasoning", "seasoning",
        "spice", "herb", "extract", "vanilla",
    ],
    "produce": [
        "spinach", "kale", "lettuce", "arugula", "broccoli", "cauliflower",
        "carrot", "celery", "cucumber", "zucchini", "squash",
        "tomato", "onion", "garlic", "ginger", "mushroom", "asparagus",
        "edamame", "corn", "pea", "bean", "lentil", "chickpea", "avocado",
        "banana", "apple", "berry", "blueberry", "strawberry", "raspberry",
        "mango", "pineapple", "orange", "lemon", "lime", "grape", "cherry",
        "peach", "pear", "watermelon", "melon", "fruit", "vegetable", "veggie",
        "cilantro", "parsley", "mint", "dill", "scallion",
        "green onion", "sweet potato", "potato", "beet", "radish",
        "mixed berries", "dried fruit", "dried cranberry", "raisin",
        "sun-dried tomato", "artichoke", "leek", "shallot", "bok choy",
        "snap pea", "snow pea", "brussels sprout", "cabbage", "fennel",
        "jalapeño", "jalapeno", "serrano", "poblano", "tomatillo",
    ],
    "protein": [
        "chicken", "turkey", "beef", "steak", "pork", "salmon", "tuna",
        "shrimp", "tilapia", "cod", "fish", "egg", "tofu", "tempeh",
        "ground beef", "ground turkey", "lamb", "bacon", "sausage",
        "protein powder", "whey", "greek yogurt", "cottage cheese",
        "edamame", "lentil", "black bean", "kidney bean",
        "deli turkey", "rotisserie chicken", "canned tuna", "canned salmon",
        "jerky", "deli meat", "lunch meat", "pepperoni", "prosciutto",
    ],
    "carb": [
        "rice", "pasta", "bread", "tortilla", "oat", "quinoa", "barley",
        "farro", "couscous", "noodle", "bagel", "wrap", "pita", "cereal",
        "granola", "cracker", "pretzel", "potato", "sweet potato",
        "flour", "cornmeal", "panko", "breadcrumb",
        "brown rice", "white rice", "rice cake", "english muffin",
        "waffle", "pancake mix", "pita bread", "sourdough", "rye bread",
    ],
    "fat": [
        "olive oil", "avocado oil", "coconut oil", "butter", "ghee",
        "almond", "walnut", "cashew", "pecan", "pistachio", "peanut",
        "nut butter", "almond butter", "peanut butter", "tahini",
        "cheese", "cream cheese", "mayo", "mayonnaise", "sesame oil",
        "flax", "chia", "hemp", "sunflower seed", "pumpkin seed",
    ],
    "hydration": [
        "water", "coconut water", "sports drink", "juice", "milk",
        "almond milk", "oat milk", "soy milk", "broth", "stock",
        "electrolyte", "tea", "smoothie",
    ],
}


def _categorize_ingredient(name: str) -> str:
    """Map a free-text ingredient name to a grocery category using keyword matching.
    Returns one of: produce, protein, carb, fat, hydration, other."""
    lower = name.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "other"


_PANTRY_STAPLES = {
    # Seasonings & spices
    "salt", "pepper", "black pepper", "white pepper", "red pepper flakes",
    "red chili flakes", "chili flakes", "cayenne", "paprika", "smoked paprika",
    "cumin", "coriander", "turmeric", "cinnamon", "nutmeg", "oregano",
    "thyme", "rosemary", "basil", "bay leaf", "garlic powder", "onion powder",
    "italian seasoning", "everything bagel seasoning", "old bay",
    # Oils & cooking fats
    "cooking spray", "olive oil", "vegetable oil", "canola oil",
    "coconut oil spray", "nonstick spray",
    # Acids & condiments
    "vinegar", "apple cider vinegar", "balsamic vinegar", "rice vinegar",
    "soy sauce", "worcestershire",
    # Baking basics
    "baking powder", "baking soda", "vanilla extract", "cornstarch",
    # Water
    "water",
}


def _is_pantry_staple(name: str) -> bool:
    """Return True if the ingredient is a common pantry staple."""
    lower = name.lower().strip()
    if lower in _PANTRY_STAPLES:
        return True
    return any(staple in lower for staple in _PANTRY_STAPLES)


def _parse_allergies(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return [a.strip() for a in raw if a and str(a).strip().lower() != "none"]
    return [a.strip() for a in str(raw).split(",") if a.strip().lower() != "none"]


def _parse_dietary(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return [d.strip() for d in raw if d and str(d).strip().lower() != "none"]
    return [d.strip() for d in str(raw).split(",") if d.strip().lower() != "none"]


def _week_start(date_str: str) -> str:
    return _get_week_start(_date.fromisoformat(date_str)).isoformat()


def _get_or_create_recipe_list(athlete_id: int, week_start: str, conn) -> int:
    conn.execute(
        "INSERT INTO recipe_lists (athlete_id, week_start) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (athlete_id, week_start),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM recipe_lists WHERE athlete_id = %s AND week_start = %s",
        (athlete_id, week_start),
    ).fetchone()["id"]


@router.get("/")
def list_recipes(category: Optional[str] = None, dietary: Optional[str] = None, avoid_allergens: Optional[str] = None):
    dietary_list = dietary.split(",") if dietary else None
    allergen_list = avoid_allergens.split(",") if avoid_allergens else None
    recipes = recipe_db.get_recipes(category=category, dietary=dietary_list, allergens_to_avoid=allergen_list)
    return {"recipes": recipes, "count": len(recipes), "powered_by": "AthFuelPath Recipe Library"}


@router.get("/categories")
def list_categories():
    from api.services.recipe_categories import RECIPE_CATEGORY_PROFILES, CATEGORY_ALIASES
    keys = sorted(set(RECIPE_CATEGORY_PROFILES.keys()) | set(CATEGORY_ALIASES.keys()))
    return {"categories": keys}


@router.post("/generate")
def generate_recipe(req: RecipeGenerateRequest, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, req.athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (req.athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
    finally:
        conn.close()

    allergies = req.allergies or _parse_allergies(athlete.get("allergies"))
    dietary = req.dietary_restrictions or _parse_dietary(athlete.get("dietary_restrictions"))

    try:
        return recipe_generator.generate_recipe(
            req.category,
            allergies=allergies,
            dietary_restrictions=dietary,
            athlete=athlete,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Recipe selection failed: {e}")


# Must be registered before /{recipe_id} — FastAPI matches in order and /for-window
# is a single-segment path that would otherwise be caught by the parameterised route.
@router.get("/for-window")
def get_recipes_for_window(
    athlete_id: int = Query(...), window_key: str = Query(...), identity=Depends(require_session),
):
    if window_key not in PROFILE_TO_DB_CATEGORIES:
        raise HTTPException(400, f"Unrecognised window_key '{window_key}'.")
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
    finally:
        conn.close()
    allergies = _parse_allergies(athlete.get("allergies"))
    dietary = _parse_dietary(athlete.get("dietary_restrictions"))
    recipes = recipe_db.get_valid_recipes(
        profile_key=window_key, allergies=allergies, dietary_restrictions=dietary,
    )
    return {"recipes": recipes, "window_key": window_key, "count": len(recipes)}


@router.get("/selections/week")
def get_week_selections(
    athlete_id: int = Query(...), week_start: str = Query(...), identity=Depends(require_session),
):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        rows = conn.execute(
            "SELECT * FROM recipe_selections WHERE athlete_id = %s AND week_start = %s"
            " ORDER BY selection_date, fueling_window_key",
            (athlete_id, week_start),
        ).fetchall()
        selections = []
        for row in rows:
            s = dict(row)
            s["recipe"] = recipe_db.get_recipe_by_id(s["recipe_id"])
            selections.append(s)
        return {"week_start": week_start, "selections": selections}
    finally:
        conn.close()


class _SelectionCreate(BaseModel):
    athlete_id: int
    selection_date: str
    fueling_window_key: str
    recipe_id: str | None = None
    servings: int = 1
    no_recipe_needed: bool = False
    custom_text: str | None = None

    @model_validator(mode="after")
    def _check_exactly_one_resolution(self):
        if self.custom_text is not None:
            self.custom_text = self.custom_text.strip() or None
        resolutions = [bool(self.recipe_id), self.no_recipe_needed, bool(self.custom_text)]
        if sum(resolutions) != 1:
            raise ValueError(
                "exactly one of recipe_id, no_recipe_needed, or custom_text is required"
            )
        return self


@router.post("/selections", status_code=201)
def create_selection(data: _SelectionCreate, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        if data.recipe_id:
            recipe_id = data.recipe_id.upper()
            if not recipe_db.get_recipe_by_id(recipe_id):
                raise HTTPException(404, f"Recipe {data.recipe_id} not found.")
        else:
            # "" is the shared sentinel for both no_recipe_needed and
            # custom_text — recipe_id stays NOT NULL at the DB layer.
            recipe_id = ""
        ws = _week_start(data.selection_date)
        # ON CONFLICT DO UPDATE, not DO NOTHING: recipe_id="" is shared by
        # BOTH no_recipe_needed and custom_text, so DO NOTHING would silently
        # drop a new custom_text (or no_recipe_needed) resolution when one of
        # the other already existed for this exact slot — the caller would
        # get 201 while nothing actually changed. A real catalog recipe_id is
        # unaffected: distinct recipe_ids never conflict (multi-recipe-per-
        # window stays additive), and reposting the SAME recipe_id just
        # updates servings in place, same as before.
        conn.execute(
            """INSERT INTO recipe_selections
               (athlete_id, week_start, selection_date, fueling_window_key, recipe_id,
                servings, no_recipe_needed, custom_text, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, sqlite_now())
               ON CONFLICT (athlete_id, week_start, fueling_window_key, recipe_id)
               DO UPDATE SET servings = excluded.servings,
                              no_recipe_needed = excluded.no_recipe_needed,
                              custom_text = excluded.custom_text,
                              updated_at = excluded.updated_at""",
            (data.athlete_id, ws, data.selection_date, data.fueling_window_key,
             recipe_id, data.servings, data.no_recipe_needed, data.custom_text),
        )
        conn.commit()
        row = conn.execute(
            """SELECT * FROM recipe_selections
               WHERE athlete_id = %s AND week_start = %s
               AND fueling_window_key = %s AND recipe_id = %s""",
            (data.athlete_id, ws, data.fueling_window_key, recipe_id),
        ).fetchone()
        return {"selection": dict(row)}
    finally:
        conn.close()


@router.delete("/selections/{selection_id}")
def delete_selection(selection_id: int, athlete_id: int = Query(...), identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        row = conn.execute(
            "SELECT id FROM recipe_selections WHERE id = %s AND athlete_id = %s",
            (selection_id, athlete_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Selection not found.")
        conn.execute("DELETE FROM recipe_selections WHERE id = %s", (selection_id,))
        conn.commit()
        return {"deleted": True}
    finally:
        conn.close()


class _SyncGroceryList(BaseModel):
    athlete_id: int
    week_start: str
    # Optional: scope the sync to exactly these selections (the
    # GrocerySelectionSheet checkbox flow). Omitted = full-week sync
    # (back-compat with the older, unscoped grocery-list screen).
    selection_ids: list[int] | None = None


@router.post("/selections/sync-grocery-list")
def sync_grocery_list(data: _SyncGroceryList, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        if data.selection_ids:
            placeholders = ",".join(["%s"] * len(data.selection_ids))
            rows = conn.execute(
                f"SELECT * FROM recipe_selections WHERE athlete_id = %s AND week_start = %s"
                f" AND id IN ({placeholders})",
                (data.athlete_id, data.week_start, *data.selection_ids),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM recipe_selections WHERE athlete_id = %s AND week_start = %s",
                (data.athlete_id, data.week_start),
            ).fetchall()
        list_id = _get_or_create_recipe_list(data.athlete_id, data.week_start, conn)
        existing_rows = conn.execute(
            "SELECT name, checked FROM recipe_list_items WHERE list_id = %s", (list_id,)
        ).fetchall()
        existing_names = {row["name"] for row in existing_rows}
        # Full delete+reinsert below rebuilds the list from every currently-
        # selected recipe's ingredients — necessary since removing a recipe
        # must remove ingredients no other selection still needs. But it was
        # wiping `checked` on EVERY add/remove of ANY recipe, not just when a
        # shared ingredient name was involved: a manually-checked item got
        # reset to unchecked the instant the user added or removed a
        # completely unrelated recipe. Capture what was checked here and
        # restore it below for any item that survives the resync.
        previously_checked = {row["name"] for row in existing_rows if row["checked"]}
        conn.execute(
            "DELETE FROM recipe_list_item_sources WHERE list_item_id IN "
            "(SELECT id FROM recipe_list_items WHERE list_id = %s)",
            (list_id,)
        )
        conn.execute("DELETE FROM recipe_list_items WHERE list_id = %s", (list_id,))
        for row in rows:
            recipe = recipe_db.get_recipe_by_id(row["recipe_id"])
            if not recipe:
                continue
            raw = recipe.get("ingredients", [])
            if isinstance(raw, str):
                ingredient_names = [i.strip() for i in raw.split(",") if i.strip()]
            elif isinstance(raw, list):
                ingredient_names = []
                for item in raw:
                    if isinstance(item, dict):
                        n = item.get("name", "").strip()
                    else:
                        n = str(item).strip()
                    if n:
                        ingredient_names.append(n)
            else:
                ingredient_names = []
            for name in ingredient_names:
                if not name:
                    continue
                is_staple = _is_pantry_staple(name)
                conn.execute(
                    "INSERT INTO recipe_list_items"
                    " (list_id, name, category, ingredient_type, checked)"
                    " VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (list_id, name, _categorize_ingredient(name),
                     "staple" if is_staple else "main",
                     1 if is_staple else 0),
                )
                item_row = conn.execute(
                    "SELECT id FROM recipe_list_items WHERE list_id = %s AND name = %s",
                    (list_id, name),
                ).fetchone()
                if item_row:
                    conn.execute(
                        "INSERT INTO recipe_list_item_sources"
                        " (list_item_id, recipe_id, recipe_name)"
                        " VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (item_row["id"], row["recipe_id"], recipe.get("name", row["recipe_id"])),
                    )
        if previously_checked:
            placeholders = ",".join(["%s"] * len(previously_checked))
            conn.execute(
                f"UPDATE recipe_list_items SET checked = 1 "
                f"WHERE list_id = %s AND name IN ({placeholders})",
                (list_id, *previously_checked),
            )
        new_names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM recipe_list_items WHERE list_id = %s", (list_id,)
            ).fetchall()
        }
        conn.commit()
        return {"synced": True, "items_added": len(new_names - existing_names), "week_start": data.week_start}
    finally:
        conn.close()


_CATEGORY_ORDER = ["produce", "protein", "carb", "fat", "hydration", "spice", "other"]
_CATEGORY_LABELS = {
    "produce":   "Produce",
    "protein":   "Protein",
    "carb":      "Carbs & Grains",
    "fat":       "Snacks & Healthy Fats",
    "hydration": "Drinks & Hydration",
    "spice":     "Spices & Seasonings",
    "other":     "Other",
}
_CATEGORY_ICONS = {
    "produce":   "leaf-outline",
    "protein":   "egg-outline",
    "carb":      "nutrition-outline",
    "fat":       "cafe-outline",
    "hydration": "water-outline",
    "spice":     "color-filter-outline",
    "other":     "ellipsis-horizontal-outline",
}


@router.get("/grocery-list")
def get_grocery_list(
    athlete_id: int = Query(...), week_start: str = Query(...), identity=Depends(require_session),
):
    from collections import defaultdict
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        list_row = conn.execute(
            "SELECT id FROM recipe_lists WHERE athlete_id = %s AND week_start = %s",
            (athlete_id, week_start),
        ).fetchone()
        if not list_row:
            return {"list_id": None, "week_start": week_start, "groups": [], "item_count": 0, "checked_count": 0}
        list_id = list_row["id"]
        item_rows = conn.execute(
            "SELECT * FROM recipe_list_items WHERE list_id = %s ORDER BY name",
            (list_id,),
        ).fetchall()
        item_ids = [r["id"] for r in item_rows]
        sources_by_item: dict = {}
        if item_ids:
            placeholders = ",".join(["%s"] * len(item_ids))
            source_rows = conn.execute(
                f"SELECT list_item_id, recipe_id, recipe_name FROM recipe_list_item_sources "
                f"WHERE list_item_id IN ({placeholders})",
                item_ids,
            ).fetchall()
            for s in source_rows:
                sources_by_item.setdefault(s["list_item_id"], []).append({
                    "recipe_id": s["recipe_id"],
                    "recipe_name": s["recipe_name"],
                })
        buckets: dict = defaultdict(list)
        for row in item_rows:
            cat = row["category"] or "other"
            buckets[cat].append({
                "id": row["id"],
                "list_id": row["list_id"],
                "name": row["name"],
                "checked": bool(row["checked"]),
                "category": cat,
                "ingredient_type": row["ingredient_type"],
                "sources": sources_by_item.get(row["id"], []),
                "created_at": row["created_at"],
            })
        groups = [
            {
                "category": cat,
                "label": _CATEGORY_LABELS[cat],
                "icon": _CATEGORY_ICONS[cat],
                "items": buckets[cat],
            }
            for cat in _CATEGORY_ORDER
            if cat in buckets
        ]
        return {
            "list_id": list_id,
            "week_start": week_start,
            "groups": groups,
            "item_count": len(item_rows),
            "checked_count": sum(1 for r in item_rows if r["checked"]),
        }
    finally:
        conn.close()


class _ToggleItem(BaseModel):
    checked: bool


@router.patch("/grocery-list/items/{item_id}")
def toggle_grocery_list_item(item_id: int, data: _ToggleItem, identity=Depends(require_session)):
    conn = get_conn()
    try:
        owner_row = conn.execute(
            "SELECT rl.athlete_id FROM recipe_list_items rli "
            "JOIN recipe_lists rl ON rl.id = rli.list_id WHERE rli.id = %s",
            (item_id,),
        ).fetchone()
        if not owner_row:
            raise HTTPException(404, f"Item {item_id} not found.")
        assert_owns_athlete(identity, dict(owner_row)["athlete_id"], conn)
        conn.execute(
            "UPDATE recipe_list_items SET checked = %s WHERE id = %s",
            (int(data.checked), item_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM recipe_list_items WHERE id = %s", (item_id,)
        ).fetchone()
        r = dict(updated)
        r["checked"] = bool(r["checked"])
        return r
    finally:
        conn.close()


@router.get("/{recipe_id}")
def get_recipe(recipe_id: str):
    recipe = recipe_db.get_recipe_by_id(recipe_id.upper())
    if not recipe:
        raise HTTPException(404, f"Recipe {recipe_id} not found.")
    return {**recipe, "powered_by": "AthFuelPath Recipe Library"}


@router.post("/swap")
def picky_eater_swap(req: RecipeSwapRequest, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, req.athlete_id, conn)
        row = conn.execute("SELECT * FROM athletes WHERE id = %s", (req.athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        allergens = _parse_allergies(dict(row).get("allergies"))
        candidates = recipe_db.get_recipes(
            category=req.meal_timing_category,
            allergens_to_avoid=allergens,
        )
        result = claude_ai.prompt4_recipe_swap(
            dict(row), req.disliked_recipe, req.meal_timing_category, candidates,
        )
        result["attribution"] = "AthFuelPath curated recipe library"
        return result
    finally:
        conn.close()
