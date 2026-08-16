# AthFuelPath — Complete Build Specification
**Version 1.0 · June 2026**
*Youth Sports Performance Nutrition Platform — Ages 9–17*

> **To any coding agent:** Build everything in this specification exactly as described. Start with the backend foundation (`main.py`, `db/setup.py`, `nutrition_calc.py`), verify it runs, then build the frontend screens in order. Every design decision, formula, API call, and edge case is resolved below. Do not ask clarifying questions — execute the spec.

---

## 1. TECH STACK — EXACT VERSIONS

### Backend
| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime |
| FastAPI | 0.111+ | API framework |
| Uvicorn | 0.29+ | ASGI server |
| SQLite | 3 (stdlib) | Database (single file `fuelup.db`) |
| Anthropic SDK | 0.28+ | Claude AI (claude-sonnet-4-6) |
| python-dotenv | 1.0+ | Environment variables |
| requests | 2.31+ | OpenWeatherMap API |
| pywebpush | 1.14+ | Push notifications (VAPID) |

### Frontend
| Tool | Version | Purpose |
|------|---------|---------|
| React | 18+ | UI framework |
| Vite | 5+ | Build tool / dev server |
| No CSS framework | — | All styles are inline React objects |

### Project structure
```
AthFuelPath/
├── api/
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   ├── routes/
│   │   ├── parents.py
│   │   ├── athletes.py
│   │   ├── events.py
│   │   ├── nutrition.py
│   │   ├── meals.py
│   │   ├── recipes.py
│   │   ├── analysis.py
│   │   ├── reports.py
│   │   ├── notifications.py
│   │   └── meal_plans.py
│   └── services/
│       ├── claude_ai.py
│       ├── nutrition_calc.py
│       ├── recipe_db.py
│       └── weather.py
├── db/
│   └── setup.py
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── AppShell.jsx
│       ├── Login.jsx
│       ├── Onboarding.jsx
│       ├── Dashboard.jsx
│       ├── HomeScreen.jsx
│       ├── NutritionDashboard.jsx
│       ├── ScheduleScreen.jsx
│       ├── MealPlannerScreen.jsx
│       ├── HydrationScreen.jsx
│       ├── ReportsScreen.jsx
│       ├── Blueprint.jsx
│       ├── ProfileScreen.jsx
│       ├── SettingsScreen.jsx
│       └── RecipesScreen.jsx
├── .env
└── requirements.txt
```

### `.env` file
```
ANTHROPIC_API_KEY=your_key_here
OPENWEATHERMAP_API_KEY=your_key_here
VAPID_PRIVATE_KEY=your_vapid_private_key
VAPID_PUBLIC_KEY=your_vapid_public_key
VAPID_CONTACT=mailto:support@yourdomain.com
SECRET_KEY=your_secret_key
```

### `requirements.txt`
```
fastapi>=0.111.0
uvicorn>=0.29.0
anthropic>=0.28.0
python-dotenv>=1.0.0
requests>=2.31.0
pywebpush>=1.14.0
pydantic>=2.0.0
```

### Running the app
```bash
# Backend
uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev   # runs on http://localhost:5173
```

---

## 2. DATABASE SCHEMA

**File:** `db/setup.py` — run with `python db/setup.py` to initialize.

All connections use `sqlite3.Row` row factory so rows behave like dicts.

```python
import sqlite3

def init_db():
    conn = sqlite3.connect("fuelup.db")
    cursor = conn.cursor()
    cursor.executescript("""

        CREATE TABLE IF NOT EXISTS parents (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name           TEXT NOT NULL,
            email               TEXT UNIQUE NOT NULL,
            consent_timestamp   TEXT NOT NULL,
            consent_confirmed   BOOLEAN DEFAULT FALSE,
            created_at          TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS athletes (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id            INTEGER REFERENCES parents(id),
            first_name           TEXT NOT NULL,
            age                  INTEGER NOT NULL,
            gender               TEXT NOT NULL,       -- Girl / Boy / Prefer not to say
            weight_lbs           REAL NOT NULL,
            height_ft            INTEGER NOT NULL,
            height_in            REAL NOT NULL,
            position             TEXT,               -- Goalkeeper/Defender/Midfielder/Forward
            competition_level    TEXT,               -- Recreational/Club/Competitive/Elite
            sweat_profile        TEXT,               -- Light/Moderate/Heavy/Very Heavy (auto-derived)
            allergies            TEXT,               -- comma-separated or "None"
            dietary_restrictions TEXT,               -- Vegetarian/Vegan/Halal/Kosher/Gluten-Free/Dairy-Free
            supplement_use       TEXT DEFAULT 'None',
            blueprint_json       TEXT,               -- stored JSON from Prompt 0
            created_at           TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id     INTEGER REFERENCES athletes(id),
            event_name     TEXT NOT NULL,
            event_type     TEXT NOT NULL,  -- game/practice/tournament/training/strength/rest
            event_date     TEXT NOT NULL,  -- YYYY-MM-DD
            start_time     TEXT,           -- HH:MM
            duration_hours REAL,
            city           TEXT,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS meal_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id  INTEGER REFERENCES athletes(id),
            logged_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            log_method  TEXT NOT NULL,   -- photo/text/quick-select/restaurant/water/meal-plan
            description TEXT,
            calories    REAL,
            carbs_g     REAL,
            protein_g   REAL,
            fat_g       REAL,
            iron_mg     REAL,
            calcium_mg  REAL,
            water_oz    REAL,
            edamam_raw  TEXT
        );

        CREATE TABLE IF NOT EXISTS daily_targets (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id       INTEGER REFERENCES athletes(id),
            target_date      TEXT NOT NULL,
            event_type       TEXT,
            total_calories   INTEGER,
            carbs_g_min      INTEGER,
            carbs_g_max      INTEGER,
            protein_g_min    INTEGER,
            protein_g_max    INTEGER,
            fat_g_min        INTEGER,
            fat_g_max        INTEGER,
            iron_mg          INTEGER,
            calcium_mg       INTEGER,
            hydration_oz_min INTEGER,
            hydration_oz_max INTEGER,
            lea_alert        BOOLEAN,
            targets_raw      TEXT
        );

        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id           INTEGER REFERENCES athletes(id),
            endpoint             TEXT NOT NULL,
            p256dh               TEXT NOT NULL,
            auth                 TEXT NOT NULL,
            remind_pregame_meal  INTEGER DEFAULT 1,
            remind_pregame_snack INTEGER DEFAULT 1,
            remind_meal_log      INTEGER DEFAULT 1,
            remind_hydration     INTEGER DEFAULT 1,
            created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(athlete_id, endpoint)
        );

        CREATE TABLE IF NOT EXISTS meal_plans (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            athlete_id      INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
            plan_date       TEXT NOT NULL,   -- YYYY-MM-DD
            slot_name       TEXT NOT NULL,   -- breakfast/lunch/dinner/snack/pre-game/pre-game-snack/halftime/post-game-recovery/between-games/bedtime-snack
            recipe_id       TEXT,            -- matches recipe_db.py id e.g. "R001"
            recipe_name     TEXT,            -- denormalized for display speed
            calories        REAL,
            carbs_g         REAL,
            protein_g       REAL,
            fat_g           REAL,
            is_ai_generated INTEGER DEFAULT 0,
            logged          INTEGER DEFAULT 0,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(athlete_id, plan_date, slot_name)
        );

        CREATE INDEX IF NOT EXISTS idx_meal_plans_athlete_date
            ON meal_plans(athlete_id, plan_date);

    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
```

**`api/database.py`**
```python
import sqlite3

def get_conn():
    conn = sqlite3.connect("fuelup.db")
    conn.row_factory = sqlite3.Row
    return conn
```

---

## 3. NUTRITION CALCULATOR — ALL FORMULAS

**File:** `api/services/nutrition_calc.py`

### RMR Formula — Everett MD 2025 (NEVER use Harris-Benedict)
```
Girls: RMR = 11.1 × wt_kg + 8.4 × ht_cm − 537
Boys:  RMR = 11.1 × wt_kg + 8.4 × ht_cm − 340
```

### Physical Activity Level (PAL) Multipliers
| Event type | Multiplier |
|-----------|-----------|
| rest | 1.55 |
| practice | 1.85 |
| training | 1.85 |
| strength | 1.85 |
| game | 2.00 |
| tournament | 2.05 |

`Total Calories = RMR × PAL`

### Carbohydrate Targets (g/kg body weight)
| Event type | Min g/kg | Max g/kg |
|-----------|---------|---------|
| rest | 4 | 5 |
| practice | 6 | 8 |
| training | 6 | 8 |
| strength | 6 | 8 |
| game | 8 | 10 |
| tournament | 10 | 12 |

### Protein Targets (g/kg body weight)
| Event type | Min g/kg | Max g/kg |
|-----------|---------|---------|
| rest | 1.2 | 1.4 |
| practice | 1.4 | 1.6 |
| training | 1.4 | 1.6 |
| strength | 1.8 | 2.0 |
| game | 1.6 | 1.8 |
| tournament | 1.8 | 2.0 |

### Fat Targets
`Fat min = Total Calories × 0.20 ÷ 9`
`Fat max = Total Calories × 0.35 ÷ 9`
**NEVER restrict fat below 20% in youth — disrupts hormones (Everett MD 2025)**

### Micronutrients (fixed, not activity-dependent)
- Iron: **15 mg/day girls**, **11 mg/day boys** (AAP/NIH DRI)
- Calcium: **1,300 mg/day ALL athletes** (AAP — peak bone mass window ages 9–17)
- Magnesium: **240 mg/day ages 9–13** (all) | **360 mg/day girls 14+** | **410 mg/day boys 14+** (NIH DRI)
- Vitamin D: **1,000 IU/day ALL athletes** (Boston Children's Hospital recommendation for active youth)

### Hydration Targets (oz/day)
| Event type | Min oz | Max oz |
|-----------|--------|--------|
| rest | 64 | 72 |
| practice | 72 | 80 |
| training | 72 | 80 |
| strength | 72 | 80 |
| game | 80 | 88 |
| tournament | 88 | 96 |

### LEA Alert Threshold
`LEA triggered if: Total Calories < 30 × FFM_kg`
`FFM_kg = wt_kg × 0.85`
This is a medical-level alert — flag to parent immediately with RD referral language.

### Event Type Normalization Map
```python
EVENT_TYPE_MAP = {
    "soccer game": "game", "soccer tournament": "tournament",
    "tournament": "tournament", "club soccer practice": "practice",
    "practice": "practice", "private soccer training": "training",
    "training": "training", "speed/agility training": "training",
    "agility": "training", "strength/conditioning": "strength",
    "strength": "strength", "yoga/flexibility/recovery": "rest",
    "yoga": "rest", "recovery": "rest", "rest": "rest",
    "pre-game day": "practice", "post-game recovery day": "rest",
    "double training day": "tournament",
}
```

### Sweat Profile Auto-Derivation
```python
def derive_sweat_profile(athlete):
    age   = athlete.get("age") or 13
    gender = (athlete.get("gender") or "").lower()
    level  = (athlete.get("competition_level") or "").lower()
    if age <= 11:   profile = "light"
    elif age <= 13: profile = "moderate"
    else:           profile = "heavy"
    if age >= 16 and "boy" in gender: profile = "very heavy"
    if level in ("elite", "competitive"):
        bump = {"light":"moderate","moderate":"heavy","heavy":"very heavy","very heavy":"very heavy"}
        profile = bump.get(profile, profile)
    return profile
```

---

## 4. CLAUDE AI PROMPTS — ALL 8 PROMPTS

**File:** `api/services/claude_ai.py`
**Model:** `claude-sonnet-4-6` for all prompts
**Base URL:** `https://api.anthropic.com`

### System Prompt (shared across all prompts)
```
You are AthFuelPath's AI nutrition engine, built exclusively on pediatric sports nutrition science for athletes ages 9–17.

SCIENCE FRAMEWORK:
- Everett MD 2025 (Stony Brook) — primary reference
- Boston Children's Hospital RDN recommendations
- AAP (American Academy of Pediatrics) guidelines
- ACSM 2016

CRITICAL RULES:
1. NEVER use Harris-Benedict or adult formulas for youth
2. RMR Girls = 11.1×wt(kg)+8.4×ht(cm)−537 | RMR Boys = 11.1×wt(kg)+8.4×ht(cm)−340 (Everett 2025)
3. NEVER restrict fat in youth — disrupts hormone production (Everett 2025)
4. Iron: Girls 15mg/day, Boys 11mg/day (AAP/NIH DRI)
5. Calcium: 1,300mg/day ALL athletes — peak bone mass window (AAP)
6. LEA Alert: calories < 30 kcal/kg fat-free mass — alert parent immediately
7. NEVER recommend artificial food dyes (Red #40, Yellow #5, Yellow #6)
8. Pre-game day is the most missed nutrition day — glycogen takes 24-48hrs to replenish
9. AthFuelPath is an EDUCATIONAL food guidance tool — NOT medical nutrition therapy

Respond ONLY with valid JSON. No markdown, no prose outside the JSON.
```

---

### Prompt 0 — Athlete Blueprint (runs once on athlete creation)
**Max tokens:** 3,000 | **Trigger:** `POST /api/athletes/` after INSERT
**Critical rule:** Claude writes narrative ONLY. All numbers come from Python `_calculated`. React renders `_calculated` numbers — never Claude text numbers.

**What it receives:** athlete dict + `targets_by_event` (output of `calc_daily_targets()` for all 5 event types)

**Returns JSON shape:**
```json
{
  "hero": {"headline": "", "parent_subtext": "", "athlete_message": ""},
  "rmr": {"parent_explanation": "", "athlete_explanation": "", "formula_note": ""},
  "calorie_range": {"parent_explanation": "", "athlete_explanation": "", "context_note": ""},
  "macros": {
    "carbs":   {"parent_explanation": "", "athlete_explanation": "", "why_it_matters": ""},
    "protein": {"parent_explanation": "", "athlete_explanation": "", "why_it_matters": ""},
    "fat":     {"parent_explanation": "", "athlete_explanation": "", "why_it_matters": ""}
  },
  "micronutrients": {
    "iron":    {"parent_explanation": "", "athlete_explanation": "", "urgency_level": "critical|important|normal", "food_sources": [], "absorption_tip": ""},
    "calcium": {"parent_explanation": "", "athlete_explanation": "", "urgency_level": "important|normal", "food_sources": []}
  },
  "lea_warning": {"triggered": false, "parent_message": null, "threshold_kcal": 0, "action_required": null},
  "unlock_cta": {"headline": "", "parent_message": "", "athlete_message": ""},
  "_meta": {"generated_by": "AthFuelPath AI — Everett MD 2025 + Boston Children's Hospital RDN + AAP", "disclaimer": "AthFuelPath provides educational food guidance — not medical nutrition therapy.", "prompt_version": "0.1"}
}
```
**Iron urgency_level rule:** MUST be `"critical"` for girls, `"important"` for boys — enforced in Python before calling Claude, never left to Claude's judgment.
**Mock fallback:** When `ANTHROPIC_API_KEY` is empty, return a Python-generated mock so development continues unblocked.

---

### Prompt 1 — Validate Daily Targets
**Max tokens:** 1,024 | **Trigger:** `GET /api/nutrition/{athlete_id}/targets?date=`

**Returns:**
```json
{"validated": true, "adjustments": [], "explanation": "2-3 sentence science-backed explanation", "parent_note": "One sentence for parent dashboard", "supplement_flag": null, "lea_alert": null}
```

---

### Prompt 2 — Daily Meal Gap Analysis
**Max tokens:** 1,500 | **Trigger:** `GET /api/analysis/{athlete_id}?date=`

Traffic light rules: green ≥ 80% of target | yellow 50–79% | red < 50%
Fuel score: 0–100 (iron, calcium, hydration weighted extra)

**Returns:**
```json
{
  "fuel_score": 0,
  "overall_status": "elite|game-ready|getting-there|needs-fuel",
  "teen_message": "",
  "traffic_lights": [{"nutrient": "Calories", "target_min": 0, "target_max": null, "logged": 0, "percentage": 0, "status": "green|yellow|red", "message": ""}],
  "gap_fix_suggestions": ["food fix 1", "food fix 2", "food fix 3"],
  "lea_alert": null,
  "iron_alert": null
}
```

---

### Prompt 3 — Weekly Parent Report
**Max tokens:** 2,000 | **Trigger:** `GET /api/reports/{athlete_id}/weekly`

**Returns:**
```json
{
  "weekly_fuel_score": 0,
  "score_trend": "improving|stable|declining",
  "what_went_well": [],
  "nutrients_to_focus_on": [{"nutrient": "Iron", "gap": "Xmg/day short", "food_fixes": [], "recipe": "R020 Iron-Boost Hummus Plate"}],
  "game_day_readiness": "",
  "hydration_report": {"days_goal_met": 0, "avg_oz": 0},
  "iron_alert": null,
  "featured_recipe": {"id": "R001", "name": "", "reason": ""},
  "report_text": "3-4 paragraph warm professional report for email/SMS",
  "legal_disclaimer": "AthFuelPath provides educational food guidance — not medical nutrition therapy. Consult your child's physician for medical concerns."
}
```

---

### Prompt 4 — Recipe Swap
**Max tokens:** 1,500 | **Trigger:** `POST /api/meals/recipe-swap`

**Returns:**
```json
{
  "alternatives": [{"name": "", "description": "", "ingredients": "", "why_it_works": "", "macros": {"calories": 0, "carbs_g": 0, "protein_g": 0, "fat_g": 0}, "prep_time_min": 0, "dietary_tags": [], "allergens": []}],
  "powered_by_note": "Nutrition data — Powered by Edamam"
}
```

---

### Prompt 5 — Personalized Hydration Plan
**Max tokens:** 1,024 | **Trigger:** `POST /api/nutrition/hydration-plan`

**Returns:**
```json
{
  "pre_event_oz": 0,
  "during_event_oz_per_20min": 0,
  "post_event_oz": 0,
  "total_day_oz": 0,
  "electrolytes_needed": false,
  "electrolyte_type": "natural sports drink|coconut water|water only",
  "sports_drink_warning": "Avoid artificial dyes (Red #40, Yellow #5, Yellow #6)...",
  "teen_message": "",
  "parent_alert": null,
  "timing_reminders": [{"when": "2hrs before", "action": "Drink Xoz water", "reason": ""}]
}
```

---

### Prompt 6 — Weekly Meal Plan Generator
**Max tokens:** 2,000 | **Trigger:** `POST /api/meal-plans/generate`

Rules enforced in prompt:
1. Only use recipe IDs from the provided list — never invent
2. Match slot's recipe_category exactly
3. No recipe repeated more than twice in one week
4. Vary protein sources across days
5. Game/tournament pre-game slots → highest-carb recipe in category
6. Rest day total calories ~15–20% lower than game day
7. Bedtime snack on practice/game/tournament → R017 or R026 (casein) unless dairy-free
8. Never assign a recipe whose allergens overlap with athlete's allergies

**Returns:**
```json
{"plan": {"YYYY-MM-DD": {"slot_name": "recipe_id_or_null"}}, "reasoning": "", "variety_check": "passed|warning"}
```

---

### Prompt 7 — Macro Estimator (free-text meal entry)
**Max tokens:** 512 | **Trigger:** `POST /api/nutrition/estimate`

**Returns:**
```json
{"calories": 0, "carbs_g": 0, "protein_g": 0, "fat_g": 0, "iron_mg": 0, "calcium_mg": 0, "confidence": "high|medium|low", "portion_note": ""}
```

---

## 5. RECIPE DATABASE — ALL 28 RECIPES

**File:** `api/services/recipe_db.py`

```python
RECIPES = [
    # Pre-game meals (3hrs before) — R001–R005
    {"id":"R001","name":"Power Pasta Bowl","category":"pre-game","timing":"3hrs before game","ingredients":"Pasta, tomato sauce, grilled chicken, parmesan, spinach, milk","macros":{"calories":650,"carbs_g":85,"protein_g":45,"fat_g":12},"dietary":["halal-adaptable"],"allergens":["gluten","dairy"]},
    {"id":"R002","name":"Brown Rice Salmon Bowl","category":"pre-game","timing":"3hrs before game","ingredients":"Brown rice, grilled salmon, edamame, avocado, cucumber, soy sauce","macros":{"calories":580,"carbs_g":72,"protein_g":38,"fat_g":18},"dietary":["gluten-free-adaptable"],"allergens":["fish","soy"]},
    {"id":"R003","name":"Turkey Wrap","category":"pre-game","timing":"3hrs before game","ingredients":"Whole wheat tortilla, turkey breast, hummus, lettuce, tomato, low-fat cheese","macros":{"calories":520,"carbs_g":65,"protein_g":38,"fat_g":14},"dietary":[],"allergens":["gluten","dairy"]},
    {"id":"R004","name":"Vegan Power Pasta","category":"pre-game","timing":"3hrs before game","ingredients":"Pasta, marinara, white beans, nutritional yeast, spinach, olive oil","macros":{"calories":600,"carbs_g":90,"protein_g":28,"fat_g":10},"dietary":["vegan","vegetarian"],"allergens":["gluten"]},
    {"id":"R005","name":"Egg + Sweet Potato Bowl","category":"pre-game","timing":"3hrs before game","ingredients":"Sweet potato, scrambled eggs, spinach, whole grain toast, OJ","macros":{"calories":540,"carbs_g":70,"protein_g":28,"fat_g":16},"dietary":["vegetarian","gluten-free-adaptable"],"allergens":["eggs","gluten"]},
    # Pre-game snacks (30–60min) — R006–R009
    {"id":"R006","name":"Banana + PB","category":"pre-game-snack","timing":"30-60min before","ingredients":"1 large banana, 2 tbsp peanut butter","macros":{"calories":280,"carbs_g":36,"protein_g":8,"fat_g":12},"dietary":["vegan","gluten-free"],"allergens":["peanuts"]},
    {"id":"R007","name":"Toast + Honey + Milk","category":"pre-game-snack","timing":"30-60min before","ingredients":"2 slices whole grain toast, 2 tbsp honey, 8oz low-fat milk","macros":{"calories":310,"carbs_g":55,"protein_g":12,"fat_g":4},"dietary":["vegetarian"],"allergens":["gluten","dairy"]},
    {"id":"R008","name":"Greek Yogurt Parfait","category":"pre-game-snack","timing":"60min before","ingredients":"Greek yogurt, granola, banana, honey","macros":{"calories":320,"carbs_g":52,"protein_g":16,"fat_g":6},"dietary":["vegetarian","gluten-free-adaptable"],"allergens":["dairy","gluten"]},
    {"id":"R009","name":"Rice Cakes + Almond Butter","category":"pre-game-snack","timing":"30-60min before","ingredients":"3 rice cakes, 2 tbsp almond butter, drizzle honey","macros":{"calories":270,"carbs_g":38,"protein_g":6,"fat_g":11},"dietary":["vegan","gluten-free"],"allergens":["tree nuts"]},
    # Halftime quick fuel — R010–R012
    {"id":"R010","name":"Orange Slices + Water","category":"halftime","timing":"Halftime","ingredients":"2 oranges (sliced), 16oz cold water","macros":{"calories":85,"carbs_g":22,"protein_g":1,"fat_g":0},"dietary":["vegan","gluten-free"],"allergens":[]},
    {"id":"R011","name":"Banana + Natural Sports Drink","category":"halftime","timing":"Halftime","ingredients":"1 banana, 16oz natural sports drink (no artificial dyes)","macros":{"calories":180,"carbs_g":44,"protein_g":1,"fat_g":0},"dietary":["vegan","gluten-free"],"allergens":[]},
    {"id":"R012","name":"Medjool Dates + Water","category":"halftime","timing":"Halftime","ingredients":"4 Medjool dates, 16oz water","macros":{"calories":240,"carbs_g":64,"protein_g":2,"fat_g":0},"dietary":["vegan","gluten-free","halal"],"allergens":[]},
    # Post-game recovery (within 30min) — R013–R017
    {"id":"R013","name":"Chocolate Milk Recovery","category":"post-game-recovery","timing":"Within 30min","ingredients":"16oz low-fat chocolate milk, 1 banana","macros":{"calories":340,"carbs_g":58,"protein_g":16,"fat_g":5},"dietary":["vegetarian","gluten-free"],"allergens":["dairy"]},
    {"id":"R014","name":"PB&J + Milk","category":"post-game-recovery","timing":"Within 30min","ingredients":"PB&J sandwich on whole grain, 8oz milk","macros":{"calories":420,"carbs_g":52,"protein_g":16,"fat_g":16},"dietary":["vegetarian"],"allergens":["gluten","dairy","peanuts"]},
    {"id":"R015","name":"Tuna + Crackers","category":"post-game-recovery","timing":"Within 30min","ingredients":"1 can tuna, whole grain crackers, 8oz milk","macros":{"calories":350,"carbs_g":38,"protein_g":32,"fat_g":6},"dietary":["gluten-free-adaptable"],"allergens":["fish","gluten","dairy"]},
    {"id":"R016","name":"Vegan Recovery Smoothie","category":"post-game-recovery","timing":"Within 30min","ingredients":"Plant protein powder, banana, oat milk, frozen berries, flaxseed","macros":{"calories":380,"carbs_g":52,"protein_g":24,"fat_g":8},"dietary":["vegan","gluten-free"],"allergens":[]},
    {"id":"R017","name":"Cottage Cheese + Pineapple","category":"post-game-recovery","timing":"Bedtime casein snack","ingredients":"1 cup cottage cheese, 1/2 cup pineapple, drizzle honey","macros":{"calories":250,"carbs_g":28,"protein_g":28,"fat_g":4},"dietary":["vegetarian","gluten-free"],"allergens":["dairy"]},
    # Practice day meals — R018–R022
    {"id":"R018","name":"Pre-Practice Oatmeal Bowl","category":"practice","timing":"2-3hrs before practice","ingredients":"Rolled oats, banana, peanut butter, honey, milk, chia seeds","macros":{"calories":480,"carbs_g":68,"protein_g":18,"fat_g":14},"dietary":["vegetarian","gluten-free-adaptable"],"allergens":["dairy","peanuts","gluten"]},
    {"id":"R019","name":"Post-Practice Rebuild Plate","category":"practice","timing":"Within 30min after practice","ingredients":"Chicken breast, brown rice, roasted broccoli, low-fat milk, olive oil","macros":{"calories":580,"carbs_g":62,"protein_g":46,"fat_g":14},"dietary":["gluten-free","halal"],"allergens":["dairy"]},
    {"id":"R020","name":"Iron-Boost Hummus Plate","category":"practice","timing":"Lunch or snack","ingredients":"Hummus, spinach, lentils, pita, bell peppers, lemon juice","macros":{"calories":420,"carbs_g":52,"protein_g":18,"fat_g":14,"iron_mg":8},"dietary":["vegan","vegetarian","halal"],"allergens":["gluten","sesame"]},
    {"id":"R021","name":"Salmon Fried Rice","category":"practice","timing":"Dinner","ingredients":"Brown rice, salmon, eggs, edamame, carrots, soy sauce, sesame oil","macros":{"calories":620,"carbs_g":58,"protein_g":42,"fat_g":18},"dietary":["gluten-free-adaptable"],"allergens":["fish","eggs","soy"]},
    {"id":"R022","name":"Strength Day Protein Plate","category":"strength","timing":"Post-strength training","ingredients":"Grilled chicken, quinoa, roasted sweet potato, Greek yogurt dip, spinach","macros":{"calories":640,"carbs_g":60,"protein_g":52,"fat_g":12},"dietary":["gluten-free"],"allergens":["dairy"]},
    # Tournament multi-day — R023–R026
    {"id":"R023","name":"Tournament Morning Plate","category":"tournament","timing":"2-3hrs before first game","ingredients":"Oatmeal pancakes, scrambled eggs, OJ, banana, honey","macros":{"calories":680,"carbs_g":95,"protein_g":28,"fat_g":14},"dietary":["vegetarian"],"allergens":["gluten","eggs","dairy"]},
    {"id":"R024","name":"Between-Games Refuel","category":"tournament","timing":"Between tournament games","ingredients":"Banana, natural sports drink, whole grain crackers, peanut butter","macros":{"calories":380,"carbs_g":62,"protein_g":10,"fat_g":10},"dietary":["vegan"],"allergens":["gluten","peanuts"]},
    {"id":"R025","name":"Tournament Recovery Dinner","category":"tournament","timing":"Tournament evening","ingredients":"Pasta, ground turkey, marinara, parmesan, side salad, milk","macros":{"calories":720,"carbs_g":82,"protein_g":48,"fat_g":16},"dietary":["halal-adaptable"],"allergens":["gluten","dairy"]},
    {"id":"R026","name":"Bedtime Casein Snack","category":"tournament","timing":"Bedtime","ingredients":"Greek yogurt, granola, honey, walnuts","macros":{"calories":320,"carbs_g":38,"protein_g":20,"fat_g":10},"dietary":["vegetarian"],"allergens":["dairy","gluten","tree nuts"]},
    # Meal prep — R027–R028
    {"id":"R027","name":"Batch Chicken + Rice + Veggies","category":"meal-prep","timing":"Meal prep — 6 servings","ingredients":"Chicken breast, brown rice, broccoli, bell peppers, olive oil, garlic, lemon","macros":{"calories":480,"carbs_g":48,"protein_g":42,"fat_g":10},"dietary":["gluten-free","halal"],"allergens":[]},
    {"id":"R028","name":"Tournament Week Prep Bowl","category":"meal-prep","timing":"Meal prep — tournament week","ingredients":"Quinoa, black beans, corn, chicken, avocado, lime, cilantro","macros":{"calories":520,"carbs_g":58,"protein_g":36,"fat_g":16},"dietary":["gluten-free","halal"],"allergens":[]},
]
```

---

## 6. API ENDPOINTS — ALL ROUTES

### Parents (`/api/parents`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Create parent account + record consent timestamp |
| GET | `/{parent_id}` | Get parent by ID |
| GET | `/login?email=` | Look up parent by email for sign-in |
| DELETE | `/test-reset?email=test@gmail.com` | Dev-only: reset test account |

### Athletes (`/api/athletes`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Create athlete → runs Prompt 0 → stores `blueprint_json` |
| GET | `/{athlete_id}` | Get athlete by ID |
| PUT | `/{athlete_id}` | Update athlete profile |
| GET | `/{athlete_id}/blueprint` | Returns `{blueprint, _calculated}` — generates on-demand if missing |

### Events (`/api/events`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Create single event |
| GET | `/{athlete_id}` | List all events for athlete |
| POST | `/{athlete_id}/ics-upload` | Parse `.ics` file → bulk insert events (filter CANCELLED) |
| DELETE | `/{event_id}` | Delete event |

**ICS parsing rules:**
- Skip any event with `STATUS:CANCELLED`
- Skip any event whose SUMMARY starts with `CANCELLED:` (case-insensitive)

### Nutrition (`/api/nutrition`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/{athlete_id}/targets?date=YYYY-MM-DD` | Calculate + validate daily targets via Prompt 1 |
| POST | `/hydration-plan` | Generate hydration plan via Prompt 5 |
| POST | `/estimate` | Estimate macros from free-text via Prompt 7 |

### Meals (`/api/meals`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/{athlete_id}` | Log a meal |
| GET | `/{athlete_id}?date=YYYY-MM-DD` | Get meal logs for a date |
| DELETE | `/{meal_id}` | Delete meal log |
| POST | `/recipe-swap` | Get 3 alternatives via Prompt 4 |

### Recipes (`/api/recipes`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Return all 28 recipes (optional ?category= filter) |
| GET | `/{recipe_id}` | Get single recipe |

### Analysis (`/api/analysis`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/{athlete_id}?date=YYYY-MM-DD` | Run Prompt 2 gap analysis for date |

### Reports (`/api/reports`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/{athlete_id}/weekly?week_start=YYYY-MM-DD` | Run Prompt 3 weekly report |

### Meal Plans (`/api/meal-plans`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/{athlete_id}?week_start=YYYY-MM-DD` | Get 7-day plan with slot skeleton derived from events |
| PUT | `/{athlete_id}/slot` | Assign recipe to a slot — upserts with denormalized macros |
| DELETE | `/{athlete_id}/slot?plan_date=&slot_name=` | Clear a slot |
| POST | `/{athlete_id}/log-slot` | Mark slot as eaten → inserts into `meal_logs`, sets `logged=1` |
| POST | `/generate` | AI full-week plan via Prompt 6 |

**Meal plan slot skeleton by event type:**
```python
SLOTS_BY_EVENT = {
    "rest":       ["breakfast", "lunch", "dinner", "snack"],
    "practice":   ["breakfast", "pre-game", "post-game-recovery", "dinner", "bedtime-snack"],
    "training":   ["breakfast", "pre-game", "post-game-recovery", "dinner", "bedtime-snack"],
    "strength":   ["breakfast", "pre-game", "post-game-recovery", "dinner", "bedtime-snack"],
    "game":       ["pre-game", "pre-game-snack", "halftime", "post-game-recovery", "dinner", "bedtime-snack"],
    "tournament": ["pre-game", "pre-game-snack", "halftime", "between-games", "post-game-recovery", "dinner", "bedtime-snack"],
}
```

**`GET /api/meal-plans/{athlete_id}` response shape:**
```json
{
  "week_start": "YYYY-MM-DD",
  "days": [{
    "date": "YYYY-MM-DD",
    "day_label": "Mon Jun 9",
    "event_type": "game",
    "event_name": "U14 Game vs Westfield",
    "calorie_target": 2800,
    "planned_calories": 1850,
    "slots": [{"slot_name": "pre-game", "recipe_category": "pre-game", "recipe_id": "R001", "recipe_name": "Power Pasta Bowl", "calories": 650, "carbs_g": 85, "protein_g": 45, "fat_g": 12, "logged": false}]
  }]
}
```

### Notifications (`/api/notifications`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/subscribe` | Save push subscription (endpoint + p256dh + auth) |
| POST | `/send/{athlete_id}` | Send push notification to athlete |

---

## 7. FRONTEND SCREENS — ALL COMPONENTS

### App state machine (`App.jsx`)
Three views: `"login"` → `"onboarding"` → `"dashboard"`
```javascript
const [view, setView] = useState("login");
const [session, setSession] = useState(null); // { parent, athletes }
const [initialTab, setInitialTab] = useState("nutrition");
const [isNewAccount, setIsNewAccount] = useState(false);
```

After login: `initialTab="home"`, `isNewAccount=false`
After onboarding: `initialTab="blueprint"`, `isNewAccount=true`

---

### Login page (`Login.jsx`)
Two-panel layout (flex row, full viewport height):

**Left hero panel** (dark green gradient `#0a3324 → #155e42`):
- RD-Approved badge
- ⚽ AthFuelPath**Youth** wordmark
- Headline: *"The complete nutrition platform for every competitive soccer athlete."*
- Subheadline: *"AI-generated, RD-approved Nutrition Blueprints — personalized to every athlete's age, training schedule, game days, dietary needs, and performance goals. Built for youth sports clubs, ages 9–17."*
- 2×2 feature grid (semi-transparent cards): 🧠 AI Nutrition Blueprints | 📅 Game-Day Fuel Protocols | 📊 Live Macro Tracking | 💧 Hydration Calculator

**Right panel** (white card, 420px wide):
- Sign-in form: email input + "Sign In →" button
- `GET /api/parents/login?email=` — 404 → show error, 200 → `onLogin(data)`
- Divider + "Create a new account" outlined button → `onNewAccount()`

---

### Onboarding wizard (`Onboarding.jsx`)
**5-step progress bar:** Age Check → Parent Consent → Athlete Profile → Review → All Set!

**Step 0 — Age Gate:**
- Input: athlete's age (integer)
- Validation: age < 9 → "AthFuelPath is for youth athletes ages 9–17..."
- Validation: age > 17 → "AthFuelPath is for ages 9–17. For athletes 18+, consult a CSSD."
- On pass: pre-fill `athlete.age` state, advance to Step 1

**Step 1 — Parent Consent:**
- Fields: Full Name (required), Email (required)
- Scrollable consent text (COPPA/California privacy compliant)
- Checkbox: "I have read and agree to all of the above consent terms."
- On submit: `POST /api/parents/` → save `parentId` → advance to Step 2
- **Replace** `purvi@dietsandlife.com` in consent text with your support email

**Step 2 — Athlete Profile (form):**
Fields collected:
- First name (required)
- Age (read-only, pre-filled from Step 0)
- Gender: Girl / Boy / Prefer not to say (dropdown, required)
- Weight in lbs (required), Height ft (required), Height in
- Soccer position: Goalkeeper / Defender / Midfielder / Forward
- Competition level: Recreational / Club / Competitive / Elite
- Food allergies: None / Peanuts / Tree nuts / Dairy / Eggs / Gluten / Soy / Shellfish (checkboxes)
- Dietary restrictions: dropdown (No restrictions / Vegetarian / Vegan / Halal / Gluten-free)
- "Continue to Review →" button → advance to Step 2.5 (NO API call yet)

**Step 2.5 — Review:**
- `<ReviewCard>` shows all entered data as a read-only table
- "← Edit" → back to Step 2
- "Submit Profile →" → `POST /api/athletes/` → on success → call `onComplete({parentId, athleteId})`
  - `onComplete` triggers `handleOnboardingComplete` in App.jsx
  - Do NOT advance to Step 3 — go directly to Blueprint

**Step 3 — Success** (only shown if `onComplete` not provided):
- Trophy icon, confirmation message, IDs shown

---

### AppShell (`AppShell.jsx`)
Navigation tabs (7 total):
```javascript
const TABS = [
  { id: "home",      label: "Home"        },
  { id: "nutrition", label: "Nutrition"   },
  { id: "schedule",  label: "Schedule"    },
  { id: "meal-plan", label: "🍳 Meal Plan" },
  { id: "blueprint", label: "🏅 Blueprint" },
  { id: "reports",   label: "Reports"     },
  { id: "hydration", label: "💧 Hydration" },
];
```

**First-time user restriction:** when `isNewAccount=true`, only show the Blueprint tab. All other tabs hidden. Clicking "Add Schedule →" in Blueprint unlocks all tabs via `onUnlockApp()`.

**Top bar:** ⚽ AthFuelPath logo + athlete name (left) | Avatar circle (initials) + ⚙ gear badge (right) → opens Settings drawer

**Settings drawer:** Right-side overlay, 380px, slide-in animation. Contains `<SettingsScreen>`.

---

### Blueprint screen (`Blueprint.jsx`)
**Fetches:** `GET /api/athletes/{athlete_id}/blueprint` → `{blueprint, _calculated}`

**First-run banner** (shown when `onAddSchedule` prop is not null):
- Dark green gradient card
- "🎉 Your Blueprint is ready!"
- Explanation text
- "➕ Add Schedule →" button → calls `onAddSchedule()` → unlocks full nav + opens Schedule tab

**Hero section:**
- Full-bleed Unsplash photo (youth soccer): `https://images.unsplash.com/photo-1579952363873-27f3bade9f55?w=800&q=80`
- Dark overlay + content on top
- Athlete name headline, science badge, parent subtext
- Frosted-glass stat strip: RMR kcal | Iron mg | Calcium g | Fat-free mass kg
- Numbers come from `_calculated` only — never from `blueprint` text

**RMR section:** Big number + athlete photo side by side

**Calorie Targets section:** 5-card grid (Rest/Practice/Game/Tournament/Strength) with emoji icons and color-coded borders

**Macronutrients — tab switcher:**
- 3 tabs: 🍞 Carbs | 🥩 Protein | 🥑 Fats
- Active tab fills with macro's color (amber/red/green)
- Each panel: food photo strip + parent explanation + athlete explanation (italic green) + "Why it matters" box

**Micronutrients — tab switcher:**
- 2 tabs: 🩸 Iron | 🦴 Calcium
- Iron tab: Red. Shows CRITICAL badge (for girls) or IMPORTANT (boys) — determined by `_calculated.iron_mg === 15`
- Each panel: food photo + urgency badge + daily target pill + explanations + food source emoji grid + absorption tip

**LEA Warning** (only renders if `bp.lea_warning.triggered === true`):
- Orange warning card with LEA threshold from `_calculated`

---

### Nutrition Dashboard (`NutritionDashboard.jsx`)
**Fetches on load:**
- Today's targets: `GET /api/nutrition/{athlete_id}/targets?date=today`
- Today's meal logs: `GET /api/meals/{athlete_id}?date=today`

**Animated SVG ring dials:**
- Large `CalorieDial` (160px): shows consumed/target kcal, percentage + status text
- Four `MacroDial` (110px each): Carbs, Protein, Fat, Hydration
- Colors: green = normal | amber ≥ 85% of max | red = exceeded
- CSS transition: `stroke-dasharray 0.55s cubic-bezier(0.4, 0, 0.2, 1)`

**Meal log form state:**
```javascript
{description: "", mealType: "", servingSize: "", numServings: 1, water_oz: 0}
```

**Calculate button (Prompt 7):**
- Fires on blur from description field: `onBlur={e => lookupMacros(e.target.value)}`
- IMPORTANT: pass `e.target.value` directly — do NOT read from state (stale closure bug)
- Scales macros by `numServings` — store `baseMacros` for 1 serving, multiply on servings change

**Meal type chips:** Breakfast | Lunch | Dinner | Snack | Pre-Game | Post-Game | Halftime

**Serving size chips:** 1 Cup | 1 Bowl | 1 Plate | 1 Piece | 1 Handful | 1 oz | Custom

**Servings chips:** 0.5 | 1 | 1.5 | 2 | 2.5 | 3

**Logged meal format:** `"Dinner: Grilled chicken with pasta, 1.5 × 1 Plate"`

---

### Schedule Screen (`ScheduleScreen.jsx`)
- List view of events by month
- Manual "Add Event" form
- ICS file upload → parse → bulk insert
- **ICS filter rules:** skip events with `STATUS:CANCELLED` or SUMMARY starting with `CANCELLED:` (case-insensitive regex)

---

### Meal Planner Screen (`MealPlannerScreen.jsx`)
**Week navigator:** Mon–Sun, prev/next week buttons

**7-column grid** (scrollable on mobile):
- Each `DayColumn`: day header + event badge + `CalorieSummaryBar` + `SlotCard`s

**CalorieSummaryBar:** `planned_calories / calorie_target` — green ≥ 90% | amber 70–89% | red < 70%

**SlotCard states:**
- Empty: dashed border, "+ Add [slot label]" → opens `RecipePicker`
- Filled: recipe name + calories + 🔄 Swap | ✕ Clear | ✓ Mark as Eaten
- Eaten: ✅ Eaten badge (disabled, prevents double-logging)

**RecipePicker:** Inline (no modal), filters by slot category + athlete allergens

**AI Generate button:** "✨ Generate Week Plan with AI" → if slots filled → overwrite warning → `POST /api/meal-plans/generate`

---

### Hydration Screen (`HydrationScreen.jsx`)
- Shows upcoming events with weather data
- Hydration plan generated by Prompt 5
- Sweat profile auto-derived (not user-editable) via `derive_sweat_profile()`
- Sports drink warning always shown: avoid Red #40, Yellow #5, Yellow #6

---

### Settings (`SettingsScreen.jsx` + `ProfileScreen.jsx`)
**SettingsScreen:** Identity card + menu rows (Athlete Profile → ProfileScreen | Notifications & Alerts) + app version + Sign Out button

**ProfileScreen:** Chip-based form for all athlete fields (same fields as Onboarding Step 2 except no age gate). Submits `PUT /api/athletes/{id}`.
- **No supplement section** — removed from app

---

## 8. PUSH NOTIFICATION SYSTEM

**Library:** `pywebpush`
**Config:** VAPID keys in `.env`

### Notification triggers and exact message text

| Trigger | When | Message |
|---------|------|---------|
| Pre-game meal reminder | 3.5 hrs before game start_time | "🍝 Fuel up time! {name}'s game is in 3.5 hours — power pasta or rice bowl now." |
| Pre-game snack reminder | 75 min before game start_time | "🍌 Quick fuel! 60 min to kickoff — banana + peanut butter or rice cakes now." |
| Post-game recovery | 20 min after game end | "🏆 Game done! Hit the 30-min recovery window — chocolate milk + banana now." |
| Daily meal log reminder | 8:00 PM if <3 meals logged | "📊 Only {n} meals logged today. Log dinner to keep {name}'s fuel score accurate." |
| Hydration reminder | Every 2 hrs on game/tournament days | "💧 Hydration check! {name} should be at {target}oz by now." |

---

## 9. LEGAL & COMPLIANCE NON-NEGOTIABLES

1. **COPPA compliance:** Parent must create account and confirm consent BEFORE any athlete data is collected. `consent_confirmed` must be `TRUE` in DB before athlete INSERT is allowed — enforced at API level (`403` if not confirmed).

2. **Consent timestamp:** Record exact UTC timestamp when parent checks the consent box.

3. **Data deletion:** Consent text must include: *"I can request complete data deletion at any time by emailing [YOUR SUPPORT EMAIL]."*

4. **Disclaimer — shown everywhere:** *"AthFuelPath provides educational food guidance — not medical nutrition therapy. Consult your child's physician for medical concerns."*
   - Shown on: Login page, Onboarding, every Blueprint page, every Report, every AI-generated plan, API root response

5. **Age gate:** Reject athletes < 9 or > 17 at both frontend (onboarding) and backend (`POST /api/athletes/` returns 400).

6. **LEA alert language:** When LEA is triggered, use: *"This is a medical-level concern — please consult a registered dietitian immediately."* Never downplay it.

7. **Iron alert for girls:** Always flag iron as `urgency_level: "critical"` for female athletes. Never `"normal"`.

8. **No artificial dyes:** Never recommend food or drinks containing Red #40, Yellow #5, or Yellow #6 in any AI output. Sports drink warning must always reference this.

9. **Science attribution:** Every report and blueprint must include: *"Science: Everett MD 2025 · Boston Children's Hospital RDN · AAP · ACSM 2016"*

10. **Edamam attribution:** Any recipe swap output must include: *"Nutrition data — Powered by Edamam"*

---

## 10. BRAND & DESIGN TOKENS

| Token | Value |
|-------|-------|
| Primary green | `#0f4c35` |
| Light green | `#1a7a54` |
| Accent green | `#6ee7b7` |
| Background gradient | `linear-gradient(135deg, #0f4c35 0%, #1a7a54 100%)` |
| Card background | `#ffffff` |
| Border | `#e5e7eb` |
| Text primary | `#111827` |
| Text secondary | `#6b7280` |
| Error red | `#dc2626` |
| Warning amber | `#d97706` |
| Success green | `#16a34a` |
| Font | `'Inter', -apple-system, sans-serif` |
| Card border radius | `16–20px` |
| All styles | Inline React style objects — no CSS framework |

---

*Built for youth sports athletes, ages 9–17. Educational food guidance — not medical nutrition therapy.*
*Science: Everett MD 2025 · Boston Children's Hospital RDN · AAP · ACSM 2016*
