"""
RAG answer orchestration for the Nutrition Coach.
Bedrock answers ONLY from approved-organization knowledge excerpts.
"""

import logging
from typing import Optional

from api.services.bedrock_client import converse_text, is_configured, parse_json_from_llm
from api.services.knowledge.approved_sources import list_sources
from api.services.knowledge.retrieval import retrieve, KnowledgeChunk
from api.services.knowledge.calculations import (
    iron_rda, calcium_rda, protein_range, hydration_needs,
    pre_training_meal_window, post_training_recovery_window, calorie_estimate,
)
from api.services.nutrition_calc import calc_age
from api.services.safety_filters import MEDICAL_INPUT_TRIGGERS, find_allergen_violations
from api.services.plate_config import normalize_allergens

logger = logging.getLogger(__name__)

_FALLBACK = (
    "I don't have enough approved information from our trusted sports nutrition sources "
    "to answer that confidently. Please consult a registered sports dietitian or the "
    "athlete's physician for personalised guidance."
)

_COACH_CAPABILITIES = """
WHAT YOU CAN HELP WITH:
- **Knowledge answers** — youth soccer sports nutrition from trusted organizations: fueling timing (pre-game, halftime, post-game, practice days), hydration, carbs/protein/recovery, iron and calcium for athletes, what *types* of foods fit a fueling window, and safe fueling habits. You can also use pre-calculated numbers when provided (iron, protein, hydration, calories).
- **Recipe recommendations** — suggest a science-backed meal or snack from FuelUp's curated recipe library for a fueling window: halftime, pre-game, post-game, breakfast, lunch, dinner, snack, or hydration. Valid library recipes are filtered for the athlete's allergies and dietary restrictions, then the best match is selected for what they asked.
- **Restaurant menu lookup** — when the athlete names a specific restaurant with a fixed menu (fast food, sit-down chain), look up that restaurant's own posted menu and suggest the better fueling picks from it.
- **Nearby restaurant suggestions** — when the athlete/parent wants restaurant ideas near their current location (no specific restaurant named), suggest 2-5 real nearby options using their device location — name, distance, rating, and hours, not menu contents.

WHAT YOU CANNOT DO:
- You do not invent new recipes — recommendations come only from FuelUp's curated recipe library.
- You do not know what is on the shelf at a specific grocery/general store (Trader Joe's, Costco, etc.) or what is in someone's fridge unless they tell you — those aren't a fixed, searchable "menu" the way a restaurant is.
- You do not have real-time or personal data (today's weather, their game schedule, their weight history).
- You are not a doctor — no diagnosis, treatment, or supplement recommendations for athletes under 18.
- You do not help with weight loss, calorie restriction, or non-nutrition topics.
""".strip()


# safety_filters.py's MEDICAL_INPUT_TRIGGERS is the maintained, more complete
# term list (used by the unused coach_service.py path) — it now backs this
# live path too, so there is one authoritative list instead of two drifting
# ones. "severe dehydration", "lose weight fast", and bare "starving" are
# kept as extras this list already caught that MEDICAL_INPUT_TRIGGERS doesn't
# cover under its own terms, to avoid losing any existing coverage.
_SAFETY_TERMS = MEDICAL_INPUT_TRIGGERS + ["severe dehydration", "lose weight fast", "starving"]


_CLASSIFIER_SYSTEM = f"""You route Nutrition Coach questions for youth soccer athletes ages 9-17.

Choose exactly ONE path. Deciding question for recipe vs knowledge: did the user EXPLICITLY say the word "recipe"/"recipes", OR ask to be shown a specific named dish? YES → recipe. NO → knowledge. When unsure, choose knowledge.

- "knowledge" — Default for ALL sports-nutrition questions AND all food/meal/snack guidance, answered with text. Includes WHY/WHEN/HOW MUCH of fueling (timing, hydration, micronutrients, recovery, calculations), evaluating something ("is my meal plan good?"), and general food guidance like "what should I eat", "suggest a meal", "give me an example of a snack", "recommend something to eat", "what's a good breakfast". These are ALL knowledge — NOT recipe — unless the user explicitly says "recipe"/"recipes" or names a specific dish to show.

- "recipe" — ONLY when the user EXPLICITLY:
  • uses the word "recipe" or "recipes" ("show me recipes", "give me a chicken recipe"), OR
  • asks to be shown a specific NAMED dish ("show me a pasta dish", "give me a smoothie").
  Generic asks for food/meals/snacks/examples WITHOUT the word "recipe" and WITHOUT a named dish are knowledge, not recipe.
  Set recipe_category to the best match:
  halftime | pre_game | post_game | breakfast | lunch | dinner | snack | hydration

- "restaurant" — The user names a SPECIFIC restaurant with a fixed, orderable menu (fast food or sit-down chain: McDonald's, Chipotle, Panda Express, Subway, etc.) and asks what to eat there, WITHOUT listing what's actually available/ordered. Extract the restaurant's name into restaurant_name.
  NOT restaurant if it's a grocery/general store (Trader Joe's, Costco, Walmart) — those have no single fixed "menu" to look up → out_of_scope instead.
  NOT restaurant if the user already lists the specific items/options themselves → knowledge (evaluate what they gave you).

- "restaurant_nearby" — The user wants restaurant SUGGESTIONS/ideas near a location, and does NOT name one specific restaurant. Signals: "near me", "nearby", "close by", "around here", "in the area", "what's around here" — OR an explicit location instead of "near me": a zip code, a city/neighborhood name, "in the 65006 area", "around downtown Ashland". Often paired with a meal-context word (healthy, post-practice, pre-game, recovery) — that's fine, still restaurant_nearby.
  NOT restaurant_nearby if a specific restaurant is named → restaurant instead.
  NOT restaurant_nearby if they're not asking about eating out anywhere → knowledge or out_of_scope per the other rules.
  IMPORTANT — a new/explicit zip, city, or place name given in THIS message is restaurant_nearby EVEN IF the prior conversation already discussed restaurants or a different location. A new location always means "search again there," never "repeat what you told me before." Extract that zip/city/place text into location_text (verbatim, e.g. "65006" or "downtown Ashland"). If the user just says "near me"/"nearby" with no explicit place named, location_text is null (their device location will be used).

- "out_of_scope" — The question cannot be answered by knowledge, recipe selection, or a restaurant lookup. Route here when:
  • Asking what to buy/eat at a specific GROCERY/general store WITHOUT listing what's available ("what should I get at Trader Joe's", "healthy stuff at Costco")
  • Real-time or personal info you don't have (weather, their schedule, what's in their pantry/fridge)
  • Non-nutrition topics (homework, sports scores, general chat)
  • Medical diagnosis, treatment, supplements for under-18, or weight-loss/dieting requests

  NOT out_of_scope if the user lists options and asks you to choose ("I have bananas and pretzels at home — which is better pre-game?") → knowledge
  NOT out_of_scope if they explicitly ask for a recipe from our library → recipe
  NOT out_of_scope if they name a specific restaurant with a fixed menu → restaurant
  NOT out_of_scope if they want nearby restaurant ideas without naming one → restaurant_nearby

{_COACH_CAPABILITIES}

Examples:
recipe (explicit "recipe"/"recipes" or a specific named dish):
- "Show me recipes" → recipe, snack
- "Give me a chicken recipe for dinner" → recipe, dinner
- "Recommend a breakfast recipe" → recipe, breakfast
- "Show me a pasta dish for the night before a game" → recipe, pre_game
- "Any halftime snack recipes?" → recipe, halftime

knowledge (ALL other food/meal guidance — text answer, NO recipe card):
- "What should I eat before practice?" → knowledge
- "Suggest a meal for game day" → knowledge
- "Give me an example of a pre-game snack" → knowledge
- "What's a good breakfast for a tournament?" → knowledge
- "Recommend something to eat" → knowledge
- "How much protein do I need?" → knowledge
- "When should I eat before a game?" → knowledge
- "Is my meal plan good?" → knowledge
- "I have bananas and pretzels at home, which is better pre-game?" → knowledge

restaurant (specific restaurant, fixed menu, nothing listed yet):
- "I am heading to Panda Express for lunch, what should I get?" → restaurant, restaurant_name: "Panda Express"
- "What's the best thing on the McDonald's menu?" → restaurant, restaurant_name: "McDonald's"
- "What should I order at Chipotle before my game?" → restaurant, restaurant_name: "Chipotle"

restaurant_nearby (wants ideas, nothing named, near their location):
- "What are some healthy restaurants near me?" → restaurant_nearby, location_text: null
- "Where can I get a good post-practice meal nearby?" → restaurant_nearby, location_text: null
- "Find a restaurant close to me with good recovery meal options" → restaurant_nearby, location_text: null
- "What's around here for lunch?" → restaurant_nearby, location_text: null
- "Give me some more healthy food restaurant options in 65006 area code" → restaurant_nearby, location_text: "65006" (a NEW zip given now — search fresh there, even though the conversation already had a restaurant list)
- "Any good places to eat in downtown Ashland?" → restaurant_nearby, location_text: "downtown Ashland"

out_of_scope (grocery/general store, real-time data, non-nutrition, medical/weight):
- "What can I eat at Trader Joe's?" → out_of_scope
- "What's healthy at Costco?" → out_of_scope

Return ONLY valid JSON, no markdown:
{{"path": "knowledge" | "recipe" | "restaurant" | "restaurant_nearby" | "out_of_scope", "recipe_category": null | "category_key", "restaurant_name": null | "restaurant name", "location_text": null | "zip/city/place from THIS message, only for restaurant_nearby"}}"""

_OUT_OF_SCOPE_SYSTEM = f"""You are FuelUp's Nutrition Coach for youth soccer athletes ages 9-17.

The athlete asked something outside what you can answer directly. Respond in a warm, conversational tone — never dismissive or rude. Briefly explain the limit in plain language, then invite them to rephrase or share details so you CAN help.

{_COACH_CAPABILITIES}

RESPONSE RULES:
1. Keep it to 2–4 short sentences. Use **bold** once for the key invite or next step.
2. Match the situation:
   - Grocery/general store without an item list → say you don't know what's on their shelves; ask them to tell you what's available and you'll help them pick the best fueling option.
   - Fridge/pantry unknown → ask what they have on hand.
   - Non-nutrition topic → gently say you're here for sports fueling questions and offer to help with food for their next practice or game.
   - Medical/weight-loss/supplements → encourage talking with a doctor or sports dietitian; do not give medical advice.
3. End with a friendly, specific invitation — not "I can't help."
4. Format as Markdown (bold + short paragraphs). No headings, lists, or citations.
5. Do NOT invent store inventory, menus, or personal data."""

_CALC_KEYWORDS = {
    "iron": lambda q, a: iron_rda(int(calc_age(dob_str=a.get("date_of_birth"), age_fallback=a.get("age", 14))), a.get("gender", "female")),
    "calcium": lambda q, a: calcium_rda(int(calc_age(dob_str=a.get("date_of_birth"), age_fallback=a.get("age", 14)))),
    "protein": lambda q, a: protein_range(a.get("weight_lbs", 120), a.get("event_type", "rest")),
    "hydration": lambda q, a: hydration_needs(a.get("weight_lbs", 120), a.get("event_type", "rest")),
    "water": lambda q, a: hydration_needs(a.get("weight_lbs", 120), a.get("event_type", "rest")),
    "calorie": lambda q, a: calorie_estimate(a.get("weight_lbs", 120), int(calc_age(dob_str=a.get("date_of_birth"), age_fallback=a.get("age", 14))), a.get("gender", "female"), a.get("event_type", "rest")),
    "calories": lambda q, a: calorie_estimate(a.get("weight_lbs", 120), int(calc_age(dob_str=a.get("date_of_birth"), age_fallback=a.get("age", 14))), a.get("gender", "female"), a.get("event_type", "rest")),
}


def _audience_suffix(persona: str | None, athlete: dict) -> str:
    """Persona-aware audience framing, appended to a system prompt. Empty
    string when persona is unset/unknown — keeps today's generic tone as the
    default for any caller that hasn't been updated to send it."""
    name = athlete.get("first_name", "the athlete")
    if persona == "parent":
        return (
            f"\n\nAUDIENCE: You are speaking to {name}'s parent/guardian, not the athlete "
            "directly. Help them understand what to prepare or look out for. Use a "
            "supportive, parent-educator tone."
        )
    if persona == "athlete":
        age = athlete.get("age", "13-17")
        return (
            f"\n\nAUDIENCE: You are speaking directly to {name}, a youth athlete (age {age}). "
            "Use encouraging, age-appropriate language — like a knowledgeable coach talking "
            "to them, not a textbook."
        )
    return ""


def _detect_safety_flag(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in _SAFETY_TERMS)


def _classify_coach_path(question: str, athlete: dict) -> dict:
    """
    LLM router: choose knowledge RAG vs recipe library selection vs restaurant
    menu lookup vs nearby-restaurant discovery vs out-of-scope redirect.
    Returns {"path": "knowledge"|"recipe"|"restaurant"|"restaurant_nearby"|"out_of_scope",
             "recipe_category": str|None, "restaurant_name": str|None,
             "location_text": str|None}. `location_text` is only ever set for
             "restaurant_nearby" — an explicit zip/city/place the athlete gave
             in THIS message, which must drive a fresh search and override any
             restaurant list from earlier in the conversation.
    """
    if not is_configured():
        return {"path": "knowledge", "recipe_category": None, "restaurant_name": None, "location_text": None}

    first = athlete.get("first_name", "athlete")
    age = athlete.get("age", "unknown")
    user = f"Athlete: {first}, age {age}.\nQuestion: {question.strip()}"

    try:
        text = converse_text(
            system=_CLASSIFIER_SYSTEM,
            user=user,
            max_tokens=80,
            temperature=0.1,
        )
        parsed = parse_json_from_llm(text)
    except Exception:
        logger.exception("Coach path classification failed for question=%r", question[:80])
        return {"path": "knowledge", "recipe_category": None, "restaurant_name": None, "location_text": None}

    path = parsed.get("path", "knowledge")
    if path not in ("knowledge", "recipe", "restaurant", "restaurant_nearby", "out_of_scope"):
        path = "knowledge"

    if path == "out_of_scope":
        return {"path": "out_of_scope", "recipe_category": None, "restaurant_name": None, "location_text": None}

    if path == "restaurant_nearby":
        location_text = (parsed.get("location_text") or "").strip() or None
        return {
            "path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None,
            "location_text": location_text,
        }

    if path == "restaurant":
        restaurant_name = (parsed.get("restaurant_name") or "").strip()
        if not restaurant_name:
            return {"path": "out_of_scope", "recipe_category": None, "restaurant_name": None, "location_text": None}
        return {
            "path": "restaurant", "recipe_category": None, "restaurant_name": restaurant_name,
            "location_text": None,
        }

    category = parsed.get("recipe_category")
    if path != "recipe":
        return {"path": "knowledge", "recipe_category": None, "restaurant_name": None, "location_text": None}

    from api.services.recipe_categories import resolve_category

    try:
        resolved = resolve_category(category or "snack")
        return {
            "path": "recipe", "recipe_category": resolved["key"], "restaurant_name": None, "location_text": None,
        }
    except ValueError:
        return {"path": "recipe", "recipe_category": "snack", "restaurant_name": None, "location_text": None}


def _answer_out_of_scope(question: str, athlete: dict, persona: str | None = None) -> dict:
    """Friendly redirect when the question is outside knowledge/recipe capabilities."""
    first_name = athlete.get("first_name", "there")

    if not is_configured():
        return {
            "answer": (
                f"**I'm not sure I can answer that one directly, {first_name}.** "
                "I'm best at sports fueling questions and recommending recipes from our "
                "science-backed library for your practice and game windows. Try asking about "
                "what to eat before a game, how much water you need, or ask me to suggest "
                "a snack for halftime."
            ),
            "format": "markdown",
            "intent": "knowledge",
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }

    user = f"Athlete's first name: {first_name}\nQuestion: {question.strip()}"
    try:
        answer_text = converse_text(
            system=_OUT_OF_SCOPE_SYSTEM + _audience_suffix(persona, athlete),
            user=user,
            max_tokens=256,
            temperature=0.4,
        )
    except Exception:
        logger.exception("Out-of-scope response failed for question=%r", question[:80])
        answer_text = (
            f"**I can't see inside a specific store or menu, {first_name}** — but if you "
            "tell me what's available, I can help you pick the best fueling option. "
            "Or ask me about timing, hydration, or request a recipe recommendation "
            "for your next window."
        )

    return {
        "answer": answer_text,
        "format": "markdown",
        "intent": "knowledge",
        "citations": [],
        "calculation": None,
        "sources": list_sources(),
    }


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


def _scan_categories(allergies: list[str], restrictions: list[str]) -> list[str]:
    """Normalize both allergies and free-text dietary restrictions/intolerances
    ('dairy-free', 'lactose intolerant') onto the same big-9 category
    vocabulary, so the output allergen scan (find_allergen_violations) also
    catches intolerances, not just allergies. Restriction phrasing that
    doesn't map onto a scannable category (vegetarian, halal, ...) is dropped
    here — the LLM prompt instruction is the only guard for those, unchanged."""
    stripped_restrictions = []
    for r in restrictions:
        t = r.strip().lower()
        for suffix in ("-free", " free", "-intolerant", " intolerant", "-intolerance", " intolerance"):
            t = t.replace(suffix, "")
        stripped_restrictions.append(t.strip())
    categories = normalize_allergens(allergies) + normalize_allergens(stripped_restrictions)
    return list(dict.fromkeys(categories))


def _format_history(history: list[dict] | None) -> str:
    if not history:
        return ""
    lines = []
    for turn in history[-12:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not content or role not in ("user", "coach"):
            continue
        label = "Athlete" if role == "user" else "Coach"
        lines.append(f"{label}: {content}")
    if not lines:
        return ""
    return "PRIOR CONVERSATION (for context only — do not repeat verbatim):\n" + "\n".join(lines) + "\n\n"


def _question_with_history(question: str, history: list[dict] | None) -> str:
    prefix = _format_history(history)
    return f"{prefix}{question}" if prefix else question


def _answer_with_recipe(question: str, athlete: dict, category: str, persona: str | None = None) -> dict:
    from api.services import recipe_generator
    from api.services.recipe_categories import resolve_category

    allergies = _parse_allergies(athlete.get("allergies"))
    dietary = _parse_dietary(athlete.get("dietary_restrictions"))

    try:
        result = recipe_generator.generate_recipe_options(
            category,
            allergies=allergies,
            dietary_restrictions=dietary,
            athlete=athlete,
            question=question,
            count=3,
        )
    except ValueError as e:
        return {
            "answer": f"I couldn't find a matching library recipe for that category: {e}",
            "format": "markdown",
            "intent": "recipe",
            "recipe": None,
            "recipes": [],
            "source_ingredients": [],
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }
    except Exception:
        logger.exception("Recipe selection failed for category=%s", category)
        return {
            "answer": (
                "Sorry, I couldn't recommend a recipe right now. "
                "Try again in a moment or ask a general fueling question."
            ),
            "format": "markdown",
            "intent": "recipe",
            "recipe": None,
            "recipes": [],
            "source_ingredients": [],
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }

    profile = resolve_category(category)
    first_name = athlete.get("first_name", "athlete")
    sport = athlete.get("sport", "their sport")
    age = athlete.get("age", "")
    position = athlete.get("position", "")
    allergies_note = f"Allergies/restrictions: {', '.join(allergies)}." if allergies else "No known allergies."
    option_count = len(result.get("recipes") or [])

    # Build conversational opener via Bedrock instead of hardcoded template
    from api.services import bedrock_client

    _opener_system = (
        "You are FuelUp's Nutrition Coach for youth athletes ages 9-17. "
        "You speak directly to the parent or athlete in a warm, knowledgeable tone. "
        "Keep responses concise — 2-3 sentences max. "
        "Never use bullet points or headers. Never mention 'the catalog' or 'our library'. "
        "Do not list the recipes — that happens separately. "
        "End with a natural offer to show specific recipes, like: "
        "'Want me to show you a couple of options that fit?' or similar."
    ) + _audience_suffix(persona, athlete)

    _opener_user = (
        f"Athlete: {first_name}, age {age}, plays {position} {sport}. "
        f"{allergies_note} "
        f"They asked: \"{question}\" "
        f"This is a {profile['label'].lower()} situation. "
        f"I have {option_count} matching recipes ready to show them. "
        f"Write a warm 2-3 sentence conversational response that addresses their question "
        f"with the key nutrition principle, then naturally offer to show the recipes."
    )

    try:
        answer = bedrock_client.converse_text(
            system=_opener_system,
            user=_opener_user,
            max_tokens=150,
            temperature=0.7,
        )
    except Exception:
        logger.warning("Conversational opener generation failed, falling back to template")
        restriction_note = f" Free of your listed allergens ({', '.join(allergies)})." if allergies else ""
        answer = (
            f"Here are **{option_count} {profile['label'].lower()}** options for {first_name}."
            f"{restriction_note} Tap one to add it to your meal plan."
        )

    return {
        "answer": answer,
        "format": "markdown",
        "intent": "recipe",
        "recipe": result["recipe"],
        "recipes": result.get("recipes", []),
        "source_ingredients": result.get("source_ingredients", []),
        "citations": [],
        "calculation": None,
        "sources": list_sources(),
    }


_RESTAURANT_SYSTEM_TEMPLATE = """You are FuelUp's Nutrition Coach for youth soccer athletes ages 9-17.

The athlete is at or heading to {restaurant_name}. Below are excerpts pulled live from {restaurant_name}'s own website/menu — NOT your usual vetted sports-nutrition sources.
{timing_block}
MENU EXCERPTS:
{excerpts_text}

STRICT RULES — follow these exactly:
1. Every single food item you name — in your main pick AND any secondary/alternative suggestion — must appear verbatim in the excerpts above, with real descriptive detail. Some excerpts below may be marketing copy with no real menu items ("fresh from the wok", "welcome to our kitchen"); ignore those and use the ones that actually list dishes.
   Do NOT add an extra option, side, or alternative that isn't in the excerpts, even as a minor aside, even with a disclaimer attached. Never write phrases like "though not explicitly listed," "if available," "typically has," "ask staff to confirm," or any other hedge that names or implies a dish you're not sure is real. If you cannot verify it from the excerpts, leave it out entirely — do not mention it "just in case."
   Example of what NOT to do: recommending a real item, then adding "...or a lettuce wrap if available (though not explicitly listed)" — that second half is forbidden. Stop at the real item.
   If NONE of the excerpts clearly name specific dishes, do NOT guess, hint, or hedge. Instead respond with exactly this (fill in the name): "I found {restaurant_name}'s page but couldn't pull specific menu items from it — tell me two or three things you're seeing on the menu and I'll help you pick the best one."
2. Favor items with real protein plus vegetables/whole grains; steer away from deep-fried or heavily sauced options — general sports-nutrition principles, not invented numbers.
3. NEVER quote specific calorie, carb, protein, or gram numbers. Use food language ("the grilled option", "a side with more veggies"), not numbers — even if the excerpts contain numbers.
4. NEVER recommend supplements for athletes under 18.
5. {allergy_block}
6. Be transparent this came from the restaurant's own posted menu, not a sports-nutrition organization — one brief phrase is enough, don't over-explain.
7. Educational food guidance only — never medical advice, never diagnose.
8. Format as **Markdown**: bold the main pick, 2-4 short sentences or a short bullet list. No headings, tables, or code blocks."""


def _meal_period_from_time(local_dt) -> str:
    """Best-guess meal period from local clock time, to frame a restaurant
    recommendation (full meal vs. quick snack). Bands are intentionally
    generous — a label to shape tone, not a precise cutoff."""
    hour = local_dt.hour + local_dt.minute / 60
    if 5 <= hour < 10.5:
        return "breakfast"
    if 10.5 <= hour < 14:
        return "lunch"
    if 14 <= hour < 17:
        return "afternoon snack"
    if 17 <= hour < 21:
        return "dinner"
    return "late-night snack"


def _restaurant_header(name: str, athlete_id: int | None, latitude: float | None, longitude: float | None) -> str:
    """A deterministic "**Name** — address" line for the top of a
    named-restaurant answer. Address comes from a verified Foursquare name
    match, never guessed — silently omitted (name-only) when coordinates are
    unavailable or no confident match is found, rather than risk a wrong
    address in a coach response."""
    header = f"**{name}**"
    if latitude is None or longitude is None:
        return header + "\n\n"
    from api.services.places.nearby_search import find_restaurant_by_name

    try:
        place = find_restaurant_by_name(name, latitude, longitude, athlete_id)
    except Exception:
        logger.exception("Restaurant address lookup failed for %r", name)
        place = None
    if place and place.address:
        header += f" — {place.address}"
    return header + "\n\n"


def _answer_with_restaurant(
    question: str,
    athlete: dict,
    restaurant_name: str,
    meal_period: str | None = None,
    city: str | None = None,
    persona: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict:
    from api.services.knowledge.web_search import search_restaurant_menu

    first_name = athlete.get("first_name", "there")
    name = (restaurant_name or "").strip()

    if not name or not is_configured():
        return _answer_out_of_scope(question, athlete, persona=persona)

    try:
        results = search_restaurant_menu(name, question, city=city)
    except Exception:
        logger.exception("Restaurant menu search failed for %r", name)
        results = []

    if not results:
        return {
            "answer": (
                f"**I couldn't find {name}'s menu online just now.** "
                "Tell me what a few options look like and I'll help you pick the best one to fuel up on."
            ),
            "format": "markdown",
            "intent": "restaurant",
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }

    allergies = _parse_allergies(athlete.get("allergies"))
    restrictions = _parse_dietary(athlete.get("dietary_restrictions"))
    allergy_parts = []
    if allergies:
        allergy_parts.append(f"Allergies — NEVER suggest items containing: {', '.join(allergies)}.")
    if restrictions:
        allergy_parts.append(f"Dietary restrictions — always respect: {', '.join(restrictions)}.")
    allergy_block = " ".join(allergy_parts) or "No known allergies or dietary restrictions."

    excerpts_text = "\n".join(
        f"\n[{i}] {r.title}\n{r.content}" for i, r in enumerate(results, 1)
    )

    timing_block = ""
    if meal_period:
        timing_block = (
            f"\nIt's currently close to {meal_period} for the athlete — frame your pick for that "
            f"(a fuller meal for lunch/dinner, something quicker and lighter for a snack window). "
            f"Mention this assumption briefly in one clause rather than asking first.\n"
        )

    system_prompt = _RESTAURANT_SYSTEM_TEMPLATE.format(
        restaurant_name=name,
        timing_block=timing_block,
        excerpts_text=excerpts_text,
        allergy_block=allergy_block,
    ) + _audience_suffix(persona, athlete)

    try:
        answer_text = converse_text(system=system_prompt, user=question, max_tokens=400, temperature=0.4)
    except Exception:
        logger.exception("Restaurant answer generation failed for %r", name)
        return {
            "answer": (
                f"**I found {name}'s menu but I'm having trouble right now, {first_name}.** "
                "Try again in a moment, or tell me what you're considering and I'll help you choose."
            ),
            "format": "markdown",
            "intent": "restaurant",
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }

    # Hard safety net: the prompt rule above ("NEVER suggest items containing
    # X") is a soft instruction the model can miss — real menu excerpts pulled
    # from the web make that easy. Scan the actual answer and regenerate/block
    # rather than trust compliance alone. See safety_filters.find_allergen_violations.
    scan_cats = _scan_categories(allergies, restrictions)
    violations = find_allergen_violations(answer_text, scan_cats)
    if violations:
        logger.warning(
            "Coach restaurant answer for athlete_id=%s mentioned possible allergen(s) %s "
            "despite instructions — regenerating", athlete.get("id"), violations,
        )
        try:
            retry_prompt = system_prompt + (
                f"\n\nSAFETY CORRECTION: your previous draft mentioned food(s) containing "
                f"{', '.join(violations)}, which this athlete cannot have. Do not name any "
                f"dish containing {', '.join(scan_cats)} anywhere in your answer, even as an aside."
            )
            answer_text = converse_text(system=retry_prompt, user=question, max_tokens=400, temperature=0.2)
            violations = find_allergen_violations(answer_text, scan_cats)
        except Exception:
            logger.exception("Restaurant answer safety-retry failed for %r", name)
            violations = violations or ["unknown"]

    if violations:
        logger.error(
            "Coach restaurant answer for athlete_id=%s still mentioned allergen(s) %s after "
            "retry — falling back to safe message", athlete.get("id"), violations,
        )
        return {
            "answer": (
                f"**I couldn't find options at {name} that clearly avoid "
                f"{', '.join(scan_cats)}, {first_name}.** "
                "Please double-check directly with the restaurant, or tell me a couple of "
                "items you're considering and I'll help you check them."
            ),
            "format": "markdown",
            "intent": "restaurant",
            "citations": [],
            "restaurant_sources": [{"title": r.title, "url": r.url} for r in results],
            "calculation": None,
            "sources": list_sources(),
        }

    header = _restaurant_header(name, athlete.get("id"), latitude, longitude)

    return {
        "answer": header + answer_text,
        "format": "markdown",
        "intent": "restaurant",
        "citations": [],
        "restaurant_sources": [{"title": r.title, "url": r.url} for r in results],
        "calculation": None,
        "sources": list_sources(),
    }


_NEARBY_RESTAURANT_SYSTEM_TEMPLATE = """You are FuelUp's Nutrition Coach for youth soccer athletes ages 9-17.

The athlete/parent wants restaurant ideas near their current location. Below are real nearby restaurants from a live restaurant-search provider — this is DISCOVERY DATA ONLY (name, distance, rating, hours, price). You do NOT have menu contents for any of these — no dish names, no ingredients, no calorie/macro data.
{location_note}{timing_block}
NEARBY CANDIDATES:
{candidates_text}

STRICT RULES — follow these exactly:
1. Only recommend restaurants that appear in the candidates above. Never invent or assume a restaurant that isn't listed.
2. You do NOT know any restaurant's menu here. Never name a specific dish, never claim a place "has" a specific healthy item. Speak only about the type of food (its cuisine/category) in general terms — e.g. "a Mediterranean spot with grilled options tend to fit well" not "get the grilled chicken bowl."
3. Recommend 2-5 of the candidates, briefly explaining why each fits the fueling context (pre-practice = lighter/carb-forward, post-practice = protein+carb recovery, general = balanced). Mention distance and describe rating/popularity qualitatively ("well-reviewed", "highly rated nearby") — do not quote raw rating decimals or review counts verbatim, the exact scale isn't meant to be read out.
4. {allergy_block}
5. NEVER quote specific calorie, carb, protein, or gram numbers — you have none for these candidates.
6. NEVER recommend supplements for athletes under 18.
7. Be transparent this is a restaurant-search result, not menu-verified — one brief phrase is enough. If they want specific menu picks for one of these, invite them to ask about that restaurant by name next.
8. Educational food guidance only — never medical advice, never diagnose.
9. If a LOCATION NOTE appears above, open your answer with one brief, honest sentence saying you couldn't find that specific place and these options are near their current location instead — never silently substitute the location without saying so.
10. Format as **Markdown**: 2-5 short recommendations, bold the restaurant names. No headings, tables, or code blocks."""


def _derive_meal_period(now: str | None) -> str | None:
    """Best-guess meal period from a client local timestamp, shared by the
    named-restaurant and nearby-restaurant paths. None if `now` is absent
    or unparseable — callers just skip the timing framing."""
    if not now:
        return None
    try:
        from datetime import datetime as _dt
        return _meal_period_from_time(_dt.fromisoformat(now))
    except (ValueError, TypeError):
        return None


def _answer_with_nearby_restaurants(
    question: str,
    athlete: dict,
    latitude: float | None,
    longitude: float | None,
    meal_period: str | None = None,
    persona: str | None = None,
    unresolved_location_text: str | None = None,
) -> dict:
    first_name = athlete.get("first_name", "there")

    if latitude is None or longitude is None or not is_configured():
        return {
            "answer": (
                f"**I'd need your location to find restaurants nearby, {first_name}.** "
                "Make sure location access is on, or tell me a neighborhood or city and "
                "I'll work from that instead."
            ),
            "format": "markdown",
            "intent": "restaurant_nearby",
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }

    from api.services.places.nearby_search import search_nearby_restaurants

    try:
        candidates = search_nearby_restaurants(latitude, longitude, athlete.get("id"))
    except Exception:
        logger.exception("Nearby restaurant search failed for athlete_id=%s", athlete.get("id"))
        candidates = []

    if not candidates:
        return {
            "answer": (
                f"**I couldn't find nearby restaurants right now, {first_name}.** "
                "Try again in a moment, or tell me a specific restaurant and I can look up its menu instead."
            ),
            "format": "markdown",
            "intent": "restaurant_nearby",
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }

    allergies = _parse_allergies(athlete.get("allergies"))
    restrictions = _parse_dietary(athlete.get("dietary_restrictions"))
    allergy_parts = []
    if allergies:
        allergy_parts.append(f"Allergies to keep in mind — favor cuisine types unlikely to center on: {', '.join(allergies)}.")
    if restrictions:
        allergy_parts.append(f"Dietary restrictions to respect: {', '.join(restrictions)}.")
    allergy_block = " ".join(allergy_parts) or "No known allergies or dietary restrictions."

    def _fmt_candidate(c, i):
        bits = [c.category]
        if c.distance_m is not None:
            bits.append(f"{c.distance_m / 1609.34:.1f} mi away")
        if c.rating is not None:
            review_note = f", {c.review_count} reviews" if c.review_count else ""
            bits.append(f"rated {c.rating}{review_note}")
        if c.price_level:
            bits.append("$" * c.price_level)
        if c.open_now is not None:
            bits.append("open now" if c.open_now else "closed now")
        return f"[{i}] {c.name} — {', '.join(bits)}. {c.address}"

    candidates_text = "\n".join(_fmt_candidate(c, i) for i, c in enumerate(candidates, 1))

    timing_block = ""
    if meal_period:
        timing_block = (
            f"\nIt's currently close to {meal_period} for the athlete — weight your picks toward that "
            f"(a fuller meal for lunch/dinner, something quicker and lighter for a snack window).\n"
        )

    location_note = ""
    if unresolved_location_text:
        location_note = (
            f'\nLOCATION NOTE: The athlete asked for "{unresolved_location_text}", but that location '
            "could not be found — the candidates below are near their current device location instead.\n"
        )

    system_prompt = _NEARBY_RESTAURANT_SYSTEM_TEMPLATE.format(
        location_note=location_note,
        timing_block=timing_block,
        candidates_text=candidates_text,
        allergy_block=allergy_block,
    ) + _audience_suffix(persona, athlete)

    try:
        answer_text = converse_text(system=system_prompt, user=question, max_tokens=400, temperature=0.4)
    except Exception:
        logger.exception("Nearby restaurant answer generation failed")
        return {
            "answer": (
                f"**I found some nearby options but I'm having trouble right now, {first_name}.** "
                "Try again in a moment."
            ),
            "format": "markdown",
            "intent": "restaurant_nearby",
            "citations": [],
            "calculation": None,
            "sources": list_sources(),
        }

    # Same hard safety net as the named-restaurant path (see there for why).
    # This path names restaurants/cuisine types, not dishes — lower risk, but
    # a restaurant name itself can contain an allergen word (e.g. "Red
    # Lobster" for a shellfish allergy), which is worth catching too.
    scan_cats = _scan_categories(allergies, restrictions)
    violations = find_allergen_violations(answer_text, scan_cats)
    if violations:
        logger.warning(
            "Coach nearby-restaurant answer for athlete_id=%s mentioned possible allergen(s) "
            "%s despite instructions — regenerating", athlete.get("id"), violations,
        )
        try:
            retry_prompt = system_prompt + (
                f"\n\nSAFETY CORRECTION: your previous draft mentioned "
                f"{', '.join(violations)}, which this athlete cannot have. Avoid any "
                f"restaurant/cuisine strongly associated with {', '.join(scan_cats)}."
            )
            answer_text = converse_text(system=retry_prompt, user=question, max_tokens=400, temperature=0.2)
            violations = find_allergen_violations(answer_text, scan_cats)
        except Exception:
            logger.exception("Nearby restaurant answer safety-retry failed")
            violations = violations or ["unknown"]

    if violations:
        logger.error(
            "Coach nearby-restaurant answer for athlete_id=%s still mentioned allergen(s) %s "
            "after retry — falling back to safe message", athlete.get("id"), violations,
        )
        return {
            "answer": (
                f"**I couldn't confidently pick nearby options that avoid "
                f"{', '.join(scan_cats)}, {first_name}.** "
                "Please double-check directly with the restaurant before ordering."
            ),
            "format": "markdown",
            "intent": "restaurant_nearby",
            "citations": [],
            "nearby_sources": [
                {"name": c.name, "place_id": c.place_id, "maps_url": c.maps_url} for c in candidates
            ],
            "calculation": None,
            "sources": list_sources(),
        }

    return {
        "answer": answer_text,
        "format": "markdown",
        "intent": "restaurant_nearby",
        "citations": [],
        "nearby_sources": [
            {"name": c.name, "place_id": c.place_id, "maps_url": c.maps_url} for c in candidates
        ],
        "calculation": None,
        "sources": list_sources(),
    }


def _maybe_calculate(question: str, athlete: dict) -> Optional[dict]:
    q = question.lower()
    for keyword, fn in _CALC_KEYWORDS.items():
        if keyword in q:
            try:
                return fn(q, athlete)
            except Exception:
                return None
    return None


def _build_system_prompt(
    chunks: list,
    calc_result: Optional[dict],
    weather: Optional[dict] = None,
    persona: str | None = None,
    athlete: Optional[dict] = None,
) -> str:
    chunks_text = ""
    if chunks:
        for i, c in enumerate(chunks, 1):
            heading = f" — {c.heading}" if c.heading else ""
            org = c.organization_name or c.source
            chunks_text += (
                f"\n[{i}] {c.title}{heading}\n"
                f"Organization: {org}\n"
                f"{c.content}\n"
            )
    else:
        chunks_text = "(No relevant knowledge excerpts found)"

    calc_text = ""
    if calc_result and "error" not in calc_result:
        calc_text = (
            f"\n\nCALCULATION RESULT (use this exact value — do not invent numbers):\n"
            f"{calc_result.get('explanation_hint', str(calc_result))}\n"
            f"Source: {calc_result.get('source', '')}"
        )

    heat_block = ""
    if weather and weather.get("heat_flag"):
        temp = weather.get("temp_f", "")
        city = weather.get("location_label") or "the athlete's area"
        heat_block = (
            f"\n\n🌡️  HEAT ADVISORY: It is {temp}°F in {city} today ({weather.get('heat_level', 'hot')} "
            f"conditions). If relevant to the question, emphasize extra hydration — 8-12 oz more fluid "
            f"per hour of activity — and mention electrolytes for any activity over 60 minutes. "
            f"Don't force this in if the question is unrelated to hydration/activity."
        )

    return f"""You are FuelUp's Nutrition Coach for youth soccer athletes ages 9-17.

YOUR CAPABILITIES:
{_COACH_CAPABILITIES}
{heat_block}

STRICT RULES — follow these exactly:
1. Answer ONLY from the knowledge excerpts provided below (from trusted sports nutrition organizations and live approved-site web results). Never invent nutritional values, formulas, or dosages.
2. If the excerpts do not contain enough information to answer an in-scope sports nutrition question, respond with exactly: "{_FALLBACK}"
3. If the question asks about a specific store, restaurant, or menu without the athlete listing what's available, do NOT guess. Respond conversationally: say you don't know what's on their shelves or menu, ask them to share what's available, and offer to help them choose the best fueling option.
4. Do NOT include inline source citations in your answer text — sources are shown separately in the app.
5. Write for a youth athlete aged 9-17 — keep language simple, supportive, and practical. Be warm, never dismissive.
6. Whenever possible, give "what to do today" guidance.
7. NEVER provide medical diagnosis, treatment advice, or supplement dosing.
8. Never recommend supplements for athletes under 18.
9. For ANY of these situations — injury, fainting, chest pain, eating disorder, severe dehydration, signs of anorexia or bulimia, extreme restriction, unintentional weight loss — respond with: "This sounds like something important to discuss with a doctor or qualified sports dietitian. Please reach out to a professional right away."
10. If the athlete's CURRENT question gives a new or different detail than PRIOR CONVERSATION (a different location, restaurant, food item, or specific ask), answer fresh from the current question and the knowledge excerpts below. NEVER just repeat, rephrase, or reuse an earlier turn's answer/list as if it already covers the new detail — PRIOR CONVERSATION is background only, not a cache to answer from.
11. Format your answer as **Markdown**:
   - Use **bold** for the main takeaway or action step
   - Use bullet lists (`- item`) when giving 2–4 practical tips
   - Keep paragraphs short (2–3 sentences max)
   - Do NOT use headings (`#`), code blocks, tables, or inline source citations
   - Plain sentences are fine when a list is not needed

KNOWLEDGE EXCERPTS:
{chunks_text}
{calc_text}""" + _audience_suffix(persona, athlete or {})


def _call_bedrock(system_prompt: str, user_question: str) -> str:
    if not is_configured():
        raise RuntimeError(
            "AWS Bedrock is not configured. Set AWS_REGION, AWS_ACCESS_KEY_ID, "
            "AWS_SECRET_ACCESS_KEY, and BEDROCK_MODEL_ID on the server."
        )
    return converse_text(system=system_prompt, user=user_question, max_tokens=512, temperature=0.3)


def _citations_from_chunks(chunks: list[KnowledgeChunk]) -> list[dict]:
    citations = []
    seen: set[str] = set()
    for c in chunks:
        key = f"{c.organization_id}:{c.title}"
        if key in seen:
            continue
        seen.add(key)
        page_url = c.source_urls[0] if c.source_urls else c.organization_url
        citations.append({
            "title": c.title,
            "source": c.organization_name or c.source,
            "organization_id": c.organization_id,
            "organization_name": c.organization_name,
            "organization_url": c.organization_url,
            "url": page_url,
            "heading": c.heading,
        })
    return citations


def _todays_event(athlete_id: int, now: str | None) -> dict | None:
    """Best-effort lookup of the athlete's event for "today" (client local
    date if `now` is given, else server date). Never raises — a lookup
    failure just means no event-venue weather, not a broken answer."""
    from datetime import date as _date, datetime as _dt
    from api.database import get_conn

    if now:
        try:
            today_str = _dt.fromisoformat(now).date().isoformat()
        except (ValueError, TypeError):
            today_str = _date.today().isoformat()
    else:
        today_str = _date.today().isoformat()

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM events WHERE athlete_id = ? AND event_date = ? ORDER BY start_time LIMIT 1",
            (athlete_id, today_str),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        logger.exception("Today's-event lookup failed for athlete_id=%s", athlete_id)
        return None
    finally:
        conn.close()


def answer_with_knowledge(
    question: str,
    athlete: dict,
    history: list[dict] | None = None,
    is_first_message: bool = False,
    recipe_category: str | None = None,
    prefer_recipe: bool = False,
    now: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    persona: str | None = None,
) -> dict:
    """
    Main RAG entry point for the Nutrition Coach.
    Returns {"answer", "citations", "calculation", "sources"}.
    `now` (client local ISO timestamp) and `latitude`/`longitude` are optional.
    Used for: restaurant-lookup meal-timing framing + location-narrowed
    search, and a heat/hydration advisory in the general knowledge answer
    (today's event venue wins over device location when both exist — see
    api.services.weather.resolve_weather). Every other path ignores them.
    `persona` ("parent"|"athlete") tunes the reply's tone/voice; unset or
    unrecognized values fall back to today's generic tone.
    """
    contextual_question = _question_with_history(question, history)
    if _detect_safety_flag(question):
        return {
            "answer": (
                "This sounds like something important to discuss with a doctor or "
                "qualified sports dietitian. Please reach out to a professional right away."
            ),
            "format": "markdown",
            "citations": [],
            "calculation": None,
            "safety_flag": True,
            "sources": list_sources(),
        }

    route = _classify_coach_path(contextual_question, athlete)
    if route["path"] == "out_of_scope":
        return _answer_out_of_scope(contextual_question, athlete, persona=persona)

    if route["path"] == "restaurant":
        meal_period = _derive_meal_period(now)

        city = None
        if latitude is not None and longitude is not None:
            from api.services.weather import reverse_geocode_city
            try:
                city = reverse_geocode_city(latitude, longitude)
            except Exception:
                logger.exception("Reverse geocode failed for %s,%s", latitude, longitude)

        return _answer_with_restaurant(
            contextual_question, athlete, route.get("restaurant_name") or "",
            meal_period=meal_period, city=city, persona=persona,
            latitude=latitude, longitude=longitude,
        )

    if route["path"] == "restaurant_nearby":
        resolved_lat, resolved_lon = latitude, longitude
        location_text = route.get("location_text")
        unresolved_location_text = None
        if location_text:
            from api.services.weather import geocode_location
            try:
                geocoded = geocode_location(location_text)
            except Exception:
                logger.exception("Forward geocode failed for %r", location_text)
                geocoded = None
            if geocoded:
                resolved_lat, resolved_lon = geocoded
            else:
                # A real place OpenWeatherMap's geocoder doesn't recognize
                # (e.g. a valid but obscure zip not in its database) must
                # never silently become a search near the athlete's actual
                # device location without saying so — that reads as wrong
                # information, not a graceful fallback. Falling back is
                # still the right call (a useful answer beats a dead end),
                # but the athlete has to be told it happened.
                unresolved_location_text = location_text
        # Use the bare `question`, not `contextual_question` — the latter
        # prefixes prior-conversation turns, and _answer_with_nearby_restaurants
        # feeds this straight to the LLM as its user message alongside a FRESH
        # candidates_text for resolved_lat/resolved_lon. Passing the history
        # blob here caused the model to blend a prior search's restaurant
        # names/city into the new answer (e.g. re-describing a previous zip's
        # results while guessing at the new zip's city), rather than treating
        # this as a clean, self-contained search — candidates_text alone
        # already provides all the grounding this answer needs.
        return _answer_with_nearby_restaurants(
            question, athlete, resolved_lat, resolved_lon,
            meal_period=_derive_meal_period(now), persona=persona,
            unresolved_location_text=unresolved_location_text,
        )

    category_for_recipe = None
    if prefer_recipe and recipe_category:
        category_for_recipe = recipe_category
    elif route["path"] == "recipe" and route.get("recipe_category"):
        category_for_recipe = route["recipe_category"]

    if category_for_recipe:
        return _answer_with_recipe(contextual_question, athlete, category_for_recipe, persona=persona)

    calc_result = _maybe_calculate(contextual_question, athlete)

    try:
        chunks = retrieve(contextual_question, top_n=5)
    except Exception:
        logger.exception("Knowledge retrieval failed for question=%r", question[:80])
        return {
            "answer": _FALLBACK,
            "format": "markdown",
            "citations": [],
            "calculation": calc_result,
            "sources": list_sources(),
        }

    if not chunks:
        return {
            "answer": _FALLBACK,
            "format": "markdown",
            "citations": [],
            "calculation": calc_result,
            "sources": list_sources(),
        }

    weather = None
    if now or (latitude is not None and longitude is not None):
        from api.services.weather import resolve_weather
        athlete_id = athlete.get("id")
        event = _todays_event(athlete_id, now) if athlete_id else None
        weather = resolve_weather(event, latitude, longitude)

    system_prompt = _build_system_prompt(chunks, calc_result, weather=weather, persona=persona, athlete=athlete)
    try:
        answer_text = _call_bedrock(system_prompt, contextual_question)
    except Exception:
        logger.exception("Bedrock call failed for Nutrition Coach")
        return {
            "answer": _FALLBACK,
            "format": "markdown",
            "citations": _citations_from_chunks(chunks),
            "calculation": calc_result,
            "sources": list_sources(),
        }

    return {
        "answer": answer_text,
        "format": "markdown",
        "citations": _citations_from_chunks(chunks),
        "calculation": calc_result,
        "sources": list_sources(),
    }
