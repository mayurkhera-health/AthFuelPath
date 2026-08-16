"""
Nutrient Timing Rules — Single Source of Truth
===============================================
All eating-window logic in AthFuelPath derives from these constants.
Source: IOC / AAP / ACSM Youth Athlete Nutrient Timing Blueprint (2025).

DO NOT modify timing offsets or clinical rationale without updating the
knowledge/nutrient_timing_blueprint.md file and re-ingesting it.
"""

# ── Window definitions ────────────────────────────────────────────────────────

WINDOWS = {
    "gas_tank": {
        "name": "Gas Tank Meal",
        "offset_hours": -3.0,          # 3–4 hrs before; we use 3.0 as the planning anchor
        "offset_range": (-4.0, -3.0),
        "focus": "High complex carbs, moderate lean protein, low fat/fiber",
        "why": (
            "Solid meals require 2–4 hours to clear the stomach. Exercising before "
            "gastric emptying is complete diverts blood flow from skeletal muscles "
            "to the digestive system, causing cramping and performance decline (ACSM)."
        ),
        "examples": [
            "Turkey & cheese sandwich on whole-wheat bread + fruit",
            "Chicken breast with brown rice and steamed broccoli",
            "Scrambled eggs with whole-grain toast and banana",
        ],
        "tags": ["Complex Carbs", "Light Protein"],
    },

    "top_off": {
        "name": "Top-Off Snack",
        "offset_hours": -0.75,         # 30–60 min before; 45 min is the planning anchor
        "offset_range": (-1.0, -0.5),
        "focus": "Simple, rapidly digestible carbs — near-zero fat or fiber",
        "why": (
            "As the activity window approaches, fat and fiber slow gastric emptying "
            "and cause GI distress. Fast carbs maintain blood glucose without "
            "burdening the digestive system."
        ),
        "examples": [
            "Banana",
            "Handful of pretzels",
            "Graham crackers",
            "Applesauce pouch",
            "Toast with honey",
            "Rice cakes",
        ],
        "tags": ["Quick Carbs"],
    },

    "during_short": {
        "name": "During Activity — Short (< 75 min)",
        "focus": "Plain water only",
        "why": (
            "For sessions under 60–75 minutes, exogenous carbohydrates provide no "
            "additional performance benefit. Plain water is sufficient for hydration."
        ),
        "hydration_target_oz_per_15min": (4, 8),
        "tags": ["Fluids"],
    },

    "during_long": {
        "name": "During Activity — Extended (≥ 75 min or tournament)",
        "focus": "30–60 g simple carbohydrates per hour + fluids + electrolytes",
        "why": (
            "Sessions exceeding 75 minutes (or extreme heat) deplete blood glucose "
            "and motor coordination. 30–60 g simple carbs per hour maintains "
            "performance. Electrolytes are mandatory on tournament days."
        ),
        "carbs_g_per_hour": (30, 60),
        "examples": [
            "Orange slices",
            "Raisins",
            "Sports drink diluted 50/50 with water",
        ],
        "tags": ["Electrolytes", "Fluids", "Quick Carbs"],
    },

    "recovery": {
        "name": "Recovery Window",
        "offset_hours": 0.5,           # Within 30 min after event end
        "offset_range": (0.0, 0.5),
        "focus": "3:1 to 4:1 ratio of carbohydrates to protein",
        "why": (
            "Insulin sensitivity is elevated immediately after exercise, creating "
            "optimal conditions for rapid glycogen resynthesis and muscle protein "
            "repair. Combining carbs with protein triggers a higher insulin response "
            "than carbs alone — opening muscle cells and halting protein breakdown "
            "(IOC Consensus Statement, Bergeron et al. 2015)."
        ),
        "carb_protein_ratio": (3, 4),  # 3:1 to 4:1
        "gold_standard": "Low-fat chocolate milk (aligns precisely with required fluid, electrolyte, and macronutrient repair ratios — validated in RCTs)",
        "examples": [
            "Low-fat chocolate milk + banana",
            "Turkey wrap",
            "Greek yogurt with berries and honey",
        ],
        "tags": ["Protein", "Fast Carbs"],
    },

    "bedtime_casein": {
        "name": "Bedtime Casein",
        "target_time": "21:00",
        "focus": "30–40 g casein protein",
        "why": (
            "Casein protein provides slow-release amino acids during sleep, proven "
            "to support overnight muscle repair in adolescent athletes (Everett MD 2025). "
            "Mandatory on practice, game, tournament, and strength days."
        ),
        "protein_target_g": (30, 40),
        "examples": [
            "Cottage cheese",
            "Greek yogurt",
        ],
        "tags": ["Casein Protein", "Light"],
        "mandatory_on": ["game", "tournament", "practice", "training", "strength", "conditioning"],
    },
}

# ── Hydration schedule ────────────────────────────────────────────────────────

HYDRATION = {
    "pre_event_early": {
        "timing": "2–4 hours before exercise",
        "target_oz": (8, 16),
        "note": "Drink before thirst — youth athletes frequently fail to recognize thirst cues until fluid deficits are established.",
    },
    "warmup": {
        "timing": "During warm-ups",
        "target_oz": 8,
    },
    "during": {
        "timing": "During exercise",
        "target_oz_per_15min": (4, 8),
        "note": "Approximately ½ to 1 cup every 15 minutes.",
    },
    "post": {
        "timing": "Post-exercise",
        "note": "Sip water or low-fat chocolate milk freely. Rehydration continues 24–48 hrs after heavy exercise.",
    },
}

# ── Core non-negotiable rules ─────────────────────────────────────────────────

CORE_RULES = [
    {
        "rule": "Never skip breakfast",
        "why": "Training in a fasted state forces growing bodies to utilize muscle tissue for fuel, hindering athletic progression and physical development.",
    },
    {
        "rule": "Calcium: 1,300 mg/day",
        "why": "Peak bone mass window — cannot recover this later. 3 servings dairy or fortified alternatives daily (AAP).",
    },
    {
        "rule": "Iron: 15 mg/day (girls)",
        "why": "52% of female adolescent athletes are iron deficient. Critical for oxygen transport in active muscles (Everett MD 2025).",
    },
    {
        "rule": "Vitamin D: support bone density",
        "why": "Works with calcium for bone mineral density during rapid growth.",
    },
    {
        "rule": "No supplements for under-18",
        "why": "Pre-workout formulas, high-dose caffeine, and creatine present safety risks to developing cardiovascular and renal systems. Fueling2Win never recommends them.",
    },
]

# ── Duration threshold for during-event carb fueling ─────────────────────────

CARB_FUELING_THRESHOLD_MINUTES = 75   # Sessions >= 75 min require carb + electrolyte fueling

# ── Prompt-ready summary (injected into Claude prompts) ──────────────────────

TIMING_BRIEF = """
FUELING2WIN NUTRIENT TIMING BLUEPRINT (IOC/AAP/ACSM — authoritative for all meal planning):

WINDOW 1 — GAS TANK MEAL (3–4 hrs before): High complex carbs + moderate lean protein + low fat/fiber.
Reason: Gastric emptying takes 2–4 hrs. Exercising before completion causes cramping and performance loss.

WINDOW 2 — TOP-OFF SNACK (30–60 min before): Simple carbs only — near-zero fat or fiber.
Reason: Fat/fiber causes GI distress in the activity window.

WINDOW 3 — DURING EVENT:
  < 75 min: Water only. No exogenous carbs needed.
  ≥ 75 min OR tournament: 30–60 g simple carbs per hour + electrolytes.
  Hydration: 4–8 oz every 15 minutes throughout.

WINDOW 4 — RECOVERY (within 30 min after event): 3:1 to 4:1 carbs:protein ratio.
Gold standard: Low-fat chocolate milk. Reason: Insulin sensitivity is peak — this is the glycogen
resynthesis and muscle repair window (IOC Bergeron et al. 2015). Missing this window significantly
delays recovery.

BEDTIME CASEIN (on active days): 30–40 g casein (cottage cheese / Greek yogurt) before sleep.
Reason: Overnight muscle repair proven in adolescent athletes.

CORE RULES: Never recommend supplements for under-18. Never skip breakfast. Calcium 1,300 mg/day.
Iron 15 mg/day for girls (52% of female teen athletes are deficient).
""".strip()
