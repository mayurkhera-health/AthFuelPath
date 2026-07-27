"""
Shared two-layer safety filter for all user-facing AI surfaces.

Layer 1 — input:  check the user's message before calling any model.
Layer 2 — output: check the model's response before showing it to the user.

Both layers must be applied on every surface that returns free-text to a
minor.  Neither layer is gated by a flag or env var — they are always-on.
The model and its prompt rules are a secondary reinforcement, not the floor.
"""

import re


# ── Trigger phrases ────────────────────────────────────────────────────────────
# Matched case-insensitively.  Any single match fires the filter.

WEIGHT_INPUT_TRIGGERS: list[str] = [
    "lose weight", "losing weight", "lost weight",
    "need to lose", "want to lose", "trying to lose",
    "drop some weight", "drop a few pounds", "drop some pounds",
    "shed some pounds", "shed a few pounds",
    "lose a few pounds", "lose some pounds",
    "cut calories", "cutting calories", "calorie deficit", "calorie cut",
    "fewer calories", "less calories", "count calories",
    "eat less", "eating less", "eat lighter", "eat a little less",
    "too fat", "too heavy", "overweight",
    "slim down", "slimming down", "thinner", "skinnier",
    "body fat percent", "bmi",
    "go on a diet", "on a diet to lose", "diet to lose",
]

# Medical triggers cover injuries, acute emergencies, and eating disorders —
# all warrant the same hard stop: refer to a doctor/professional, no protocol.
MEDICAL_INPUT_TRIGGERS: list[str] = [
    # Injuries
    "strain", "sprain", "fracture", "stress fracture",
    "torn", "tear", "concussion",
    "shin splints", "tendinitis", "plantar fasciitis", "bursitis",
    "pulled muscle", "pulled my hamstring", "pulled my quad",
    "pulled my calf", "pulled my groin",
    "ligament", "tendon", "cartilage", "acl", "mcl", "pcl",
    "knee pain", "knee hurts", "knee aching", "knee clicking",
    "knee popping", "knee swollen",
    "hip pain", "hip hurts",
    "ankle pain", "ankle hurts", "ankle swollen",
    "shoulder pain", "shoulder hurts",
    "hamstring pain", "hamstring hurts", "hamstring sore for",
    "shin pain", "shin hurts",
    "back pain", "back hurts",
    "wrist pain", "wrist hurts",
    "elbow pain", "elbow hurts",
    "has been sore for", "been hurting for",
    "is it a strain", "is it a tear", "is it a sprain",
    "do i have a",
    "what's wrong with my", "what did i do to my",
    "swelling", "swollen",
    "diagnosis", "diagnose",
    # Acute medical emergencies
    "chest pain", "can't breathe", "cannot breathe",
    "faint", "fainting", "fainted", "passing out", "passed out",
    "vomiting blood", "seizure", "unconscious",
    # Eating disorders
    "eating disorder", "anorexia", "bulimia",
    "purge", "purging",
    "binge", "binge eating", "binging", "bingeing",
    "starving myself", "stop eating", "stopped eating",
    "not eating", "not been eating", "haven't been eating", "haven't eaten",
]

# Output triggers are wider and paraphrase-aware — over-firing is the safe
# direction when the output filter is the last line before a minor sees content.
WEIGHT_OUTPUT_TRIGGERS: list[str] = [
    "lose weight", "losing weight", "weight loss",
    "cut calories", "calorie deficit", "fewer calories", "less calories",
    "slim down", "slimming",
    "sustainable weight", "healthy weight loss",
    "help you lose", "talk about losing", "discuss losing",
]

MEDICAL_OUTPUT_TRIGGERS: list[str] = [
    # Diagnoses — naming, implying, or ruling out
    "sounds like a", "seems like a", "appears to be a",
    "probably a ", "likely a ", "might be a ", "could be a ",
    "it's more like", "it's probably a", "it's likely a",
    "that's a strain", "that's a sprain", "that's a tear", "that's a fracture",
    "you've strained", "you've torn", "you've sprained",
    "not a full tear", "not a tear", "not a fracture", "not a serious injury",
    "just a minor", "just a strain", "just a sprain",
    "overuse strain", "overuse injury", "muscle strain", "muscle tear",
    "microtear", "micro-tear",
    # Ice / cold protocols
    "ice it", "ice the", "apply ice", "put ice", "use ice", "try ice",
    "ice pack", "cold pack", "cold compress", "icing your",
    # Heat protocols
    "use heat", "try heat", "heat pack", "warm compress", "heating pad",
    # Rest / avoidance protocols
    "rest for", "rest your",
    "take a few days off", "take a day or two off",
    "avoid running", "avoid practice", "skip practice",
    "take it easy on your",
    # Compression / elevation / bracing
    "compression sleeve", "wrap it", "brace it", "athletic tape", "kinesio",
    "keep it elevated", "elevate your",
    # Medication
    "ibuprofen", "advil", "tylenol", "acetaminophen",
    "anti-inflammatory medication", "nsaid", "pain reliever", "pain medication",
    # Manual therapy protocols
    "gentle stretching", "light stretching", "stretch it out",
    "foam roll", "foam roller",
    # RICE protocol (not the food)
    "r.i.c.e", "rest, ice, compression",
    # Prognosis
    "should heal", "heal on its own", "you'll be fine in",
    "should be better in", "back to normal in",
    # Physical therapy (shouldn't be prescribing this)
    "physical therapy", "physiotherapist",
]


# ── Fixed responses ────────────────────────────────────────────────────────────
# Not model-generated.  Exact strings shown to the user when a filter fires.

WEIGHT_INPUT_RESPONSE: str = (
    "Fueling well is what makes you fast — your body needs energy to perform "
    "at its best, not less food. If you have questions about your body, your "
    "team's dietitian or a trusted adult is the right person to talk to. "
    "I'm here for fueling questions whenever you're ready."
)

MEDICAL_INPUT_RESPONSE: str = (
    "That's outside what I can help with — please talk to your coach or a "
    "sports-medicine doctor, they're the right people for that. I'm here for "
    "nutrition and fueling questions whenever you're ready."
)

# Output weight response is warmer — the model volunteering body-image content
# unprompted is a vulnerable moment, not a direct ask.
WEIGHT_OUTPUT_RESPONSE: str = (
    "I hear you, and those feelings are real. This is worth talking through "
    "with someone who really knows you — a parent, trusted adult, or your "
    "team's dietitian. I'm here for fueling and game-day questions whenever "
    "you need me."
)

MEDICAL_OUTPUT_RESPONSE: str = (
    "That's outside what I can help with — please talk to your coach or a "
    "sports-medicine doctor, they're the right people for that. I'm here for "
    "nutrition and fueling questions whenever you're ready."
)


# ── Filter functions ───────────────────────────────────────────────────────────

def check_input_safe(message: str) -> str | None:
    """
    Returns a fixed safe response if the message triggers a hard stop.
    Returns None if the message is safe to pass to the model.
    Call this BEFORE any model invocation.
    """
    msg = message.lower()
    if any(p in msg for p in WEIGHT_INPUT_TRIGGERS):
        return WEIGHT_INPUT_RESPONSE
    if any(p in msg for p in MEDICAL_INPUT_TRIGGERS):
        return MEDICAL_INPUT_RESPONSE
    return None


def check_output_safe(response: str) -> str | None:
    """
    Returns a fixed safe response if the model's output contains forbidden
    content.  Returns None if the response is safe to show.
    Call this AFTER the model returns, BEFORE the response reaches the user.
    """
    resp = response.lower()
    if any(p in resp for p in WEIGHT_OUTPUT_TRIGGERS):
        return WEIGHT_OUTPUT_RESPONSE
    if any(p in resp for p in MEDICAL_OUTPUT_TRIGGERS):
        return MEDICAL_OUTPUT_RESPONSE
    return None


# ── Allergen output scan ───────────────────────────────────────────────────────
# The Coach's restaurant-lookup paths pull real, untrusted menu text from the
# web and rely on a prompt instruction ("never suggest X") to avoid an
# athlete's allergens — a soft check an LLM can and does miss. This is the
# hard check behind it: scan the model's actual answer for concrete dish/
# ingredient words matching the athlete's known allergens (already normalized
# to the big-9 vocabulary via plate_config.normalize_allergens) before the
# response ever reaches the user. Broader than plate_config's synonym map,
# which only covers athlete-entered *input* variants — this matches menu-
# style *output* language.
ALLERGEN_SCAN_KEYWORDS: dict[str, list[str]] = {
    "dairy": [
        "milk", "cheese", "cream", "butter", "yogurt", "yoghurt", "ranch",
        "alfredo", "parmesan", "mozzarella", "cheddar", "queso", "ice cream",
        "custard", "brie", "feta", "gouda", "buttermilk", "provolone", "ricotta",
    ],
    "egg": ["egg", "eggs", "mayonnaise", "mayo", "meringue", "frittata", "omelet", "omelette"],
    "fish": [
        "fish", "salmon", "tuna", "cod", "tilapia", "anchovy", "anchovies",
        "halibut", "trout", "sardine", "mahi", "bass", "snapper", "catfish", "swordfish",
    ],
    "shellfish": [
        "shrimp", "prawn", "crab", "lobster", "scallop", "clam", "mussel",
        "oyster", "crawfish", "crayfish", "calamari", "squid", "octopus", "langoustine",
    ],
    "tree nuts": [
        "almond", "walnut", "cashew", "pecan", "pistachio", "hazelnut",
        "macadamia", "pine nut", "brazil nut",
    ],
    "peanut": ["peanut", "peanuts", "groundnut"],
    "gluten": [
        "wheat", "bread", "flour", "pasta", "noodle", "bun", "breaded",
        "batter", "crouton", "tortilla", "cracker", "pastry", "dough", "gluten",
    ],
    "soy": ["soy", "soya", "tofu", "edamame", "tempeh", "teriyaki"],
    "sesame": ["sesame", "tahini"],
}


def find_allergen_violations(text: str, allergen_categories: list[str]) -> list[str]:
    """Scan generated text for dish/ingredient words matching the athlete's
    known allergens/intolerances. `allergen_categories` must already be
    normalized to the big-9 vocabulary. Returns the categories that appear
    to be violated — empty means the text looks safe. Call this AFTER any
    model call that can name specific foods, BEFORE the response reaches
    the user."""
    if not allergen_categories:
        return []
    lowered = text.lower()
    hits = []
    for cat in allergen_categories:
        for kw in ALLERGEN_SCAN_KEYWORDS.get(cat, [cat]):
            if re.search(rf"\b{re.escape(kw)}\b", lowered):
                hits.append(cat)
                break
    return hits
