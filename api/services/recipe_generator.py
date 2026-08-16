"""Recipe selection from the AthFuelPath curated recipe library via agent choice."""

import json

from api.services import claude_ai, recipe_db
from api.services.bedrock_client import converse_text, parse_json_from_llm
from api.services.recipe_categories import resolve_category


def _recipe_db_to_response(db_recipe: dict, profile_key: str) -> dict:
    macros = db_recipe["macros"]
    ingredients = [i.strip() for i in db_recipe["ingredients"].split(",") if i.strip()]
    tags = list(dict.fromkeys([profile_key, *db_recipe.get("dietary", [])]))
    return {
        "name": db_recipe["name"],
        "category": profile_key,
        "calories": macros["calories"],
        "protein_g": macros["protein_g"],
        "carbs_g": macros["carbs_g"],
        "fat_g": macros["fat_g"],
        "ingredients": ingredients,
        "preparation_notes": (
            f"Best timing: {db_recipe['timing']}. "
            "Combine the listed ingredients into a balanced serving."
        ),
        "tags": tags,
    }


def _compact_recipes(recipes: list[dict]) -> list[dict]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "timing": r["timing"],
            "ingredients": r["ingredients"],
            "calories": r["macros"]["calories"],
            "protein_g": r["macros"]["protein_g"],
            "carbs_g": r["macros"]["carbs_g"],
            "fat_g": r["macros"]["fat_g"],
            "dietary": r["dietary"],
            "allergens": r["allergens"],
        }
        for r in recipes
    ]


def _choose_recipes_with_agent(
    candidates: list[dict],
    profile: dict,
    question: str | None,
    allergies: list | None,
    dietary_restrictions: list | None,
    athlete: dict | None,
    count: int = 3,
) -> list[dict]:
    restrictions = []
    if allergies:
        restrictions.append(f"Allergens to avoid: {', '.join(allergies)}")
    if dietary_restrictions:
        restrictions.append(f"Dietary restrictions: {', '.join(dietary_restrictions)}")
    restrictions_text = "\n".join(restrictions) or "None"

    athlete_ctx = ""
    if athlete:
        athlete_ctx = (
            f"Athlete: {athlete.get('first_name', 'athlete')}, "
            f"age {athlete.get('age', 'unknown')}, "
            f"position {athlete.get('position', 'unknown')}."
        )

    user_request = question or f"Suggest a {profile['label'].lower()} recipe."
    pick_count = min(max(count, 1), len(candidates))

    prompt = f"""You are AthFuelPath's recipe selector for youth soccer athletes ages 9-17.

AthFuelPath provides food education guidance — not medical nutrition therapy.
Never recommend supplements for athletes under 18.

You are selecting existing recipes from AthFuelPath's curated recipe library — not writing new ones.

USER REQUEST: {user_request}

CATEGORY: {profile['label']}
REQUIREMENTS: {profile['requirements']}
TARGET CALORIES: {profile['target_calories']['min']}–{profile['target_calories']['max']} kcal
RESTRICTIONS: {restrictions_text}
{athlete_ctx}

AVAILABLE RECIPES — these are the only valid options. You MUST pick recipe_ids only from this list:
{json.dumps(_compact_recipes(candidates), indent=2)}

RULES:
1. Return exactly {pick_count} distinct recipe_id values when possible.
2. Order them from best match to next-best for the user's request.
3. Pick variety when the user has no strong preference.
4. Never invent recipes, ingredients, or IDs.

Return ONLY valid JSON:
{{"recipe_ids": ["R010", "R015", "R020"]}}"""

    text = converse_text(
        system=claude_ai.SCIENCE_SYSTEM,
        user=prompt,
        max_tokens=256,
        temperature=0.3,
    )
    parsed = parse_json_from_llm(text)
    by_id = {r["id"]: r for r in candidates}

    raw_ids = parsed.get("recipe_ids")
    if not isinstance(raw_ids, list):
        single = parsed.get("recipe_id")
        raw_ids = [single] if single else []

    selected: list[dict] = []
    seen: set[str] = set()
    for rid in raw_ids:
        rid = str(rid).upper()
        if rid in by_id and rid not in seen:
            selected.append(by_id[rid])
            seen.add(rid)
        if len(selected) >= pick_count:
            break

    for candidate in candidates:
        if candidate["id"] not in seen:
            selected.append(candidate)
            seen.add(candidate["id"])
        if len(selected) >= pick_count:
            break

    return selected[:pick_count]


def _choose_recipe_with_agent(
    candidates: list[dict],
    profile: dict,
    question: str | None,
    allergies: list | None,
    dietary_restrictions: list | None,
    athlete: dict | None,
) -> dict:
    return _choose_recipes_with_agent(
        candidates,
        profile,
        question,
        allergies,
        dietary_restrictions,
        athlete,
        count=1,
    )[0]


def generate_recipe_options(
    category: str,
    allergies: list | None = None,
    dietary_restrictions: list | None = None,
    athlete: dict | None = None,
    question: str | None = None,
    count: int = 3,
) -> dict:
    """
    Returns up to `count` recipe options from the library for the Nutrition Coach.
    Shape: { recipes: [{recipe, source_ingredients}, ...], recipe, source_ingredients, ingredient_source }
    """
    profile = resolve_category(category)
    candidates = recipe_db.get_valid_recipes(
        profile["key"],
        allergies=allergies,
        dietary_restrictions=dietary_restrictions,
    )
    if not candidates:
        raise ValueError(
            f"No recipe found for category '{category}' "
            "with the given allergies and dietary restrictions."
        )

    db_recipes = _choose_recipes_with_agent(
        candidates,
        profile,
        question,
        allergies,
        dietary_restrictions,
        athlete,
        count=count,
    )

    options = []
    for db_recipe in db_recipes:
        ingredients = [i.strip() for i in db_recipe["ingredients"].split(",") if i.strip()]
        options.append({
            "recipe": _recipe_db_to_response(db_recipe, profile["key"]),
            "source_ingredients": ingredients,
        })

    first = options[0]
    return {
        "recipes": options,
        "recipe": first["recipe"],
        "source_ingredients": first["source_ingredients"],
        "ingredient_source": "recipe_library",
    }


def generate_recipe(
    category: str,
    allergies: list | None = None,
    dietary_restrictions: list | None = None,
    athlete: dict | None = None,
    question: str | None = None,
) -> dict:
    """
    Returns { recipe, source_ingredients, ingredient_source } matching the mobile RecipeGenerateResponse shape.
    Sends all valid library recipes to the agent, which picks the best match for the request.
    """
    result = generate_recipe_options(
        category,
        allergies=allergies,
        dietary_restrictions=dietary_restrictions,
        athlete=athlete,
        question=question,
        count=1,
    )
    return {
        "recipe": result["recipe"],
        "source_ingredients": result["source_ingredients"],
        "ingredient_source": result["ingredient_source"],
    }
