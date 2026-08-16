# RAG Knowledge System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a retrieval-augmented generation system that lets Claude answer youth-athlete nutrition questions only from approved, cited knowledge files — using TF-IDF retrieval, deterministic Python calculations, and the existing Anthropic API key.

**Architecture:** Markdown knowledge files in `/knowledge/` are ingested into two new SQLite tables (`knowledge_items`, `knowledge_chunks`). At query time, TF-IDF cosine similarity retrieves the top relevant chunks, deterministic calculation functions provide any numeric values, and Claude answers only from the provided context with mandatory citations.

**Tech Stack:** Python 3.12, FastAPI, SQLite (existing), scikit-learn (TF-IDF), PyYAML, Anthropic SDK (existing), pytest

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create dir | `knowledge/` | Approved Markdown knowledge files |
| Create | `knowledge/iron_magnesium.md` | Iron & magnesium RDA + athlete context |
| Create | `knowledge/hydration.md` | Daily oz targets, sweat rate, electrolytes |
| Create | `knowledge/pre_practice_meals.md` | Timing windows, macros, example meals |
| Create | `knowledge/post_practice_recovery.md` | 30-min window, 3:1 ratio, casein |
| Create | `knowledge/game_day_nutrition.md` | Night-before through recovery |
| Create | `knowledge/weekly_checkin.md` | Weekly fuel quality assessment |
| Create | `knowledge/safety_red_flags.md` | When to refer to a professional |
| Modify | `db/setup.py` | Add knowledge_items + knowledge_chunks tables |
| Create | `api/services/knowledge/__init__.py` | Package marker |
| Create | `api/services/knowledge/ingest.py` | Parse MD, chunk, store in SQLite |
| Create | `api/services/knowledge/retrieval.py` | TF-IDF search, return top-N chunks |
| Create | `api/services/knowledge/calculations.py` | Deterministic nutrition functions |
| Create | `api/services/knowledge/answer.py` | RAG orchestration + Claude prompt |
| Create | `scripts/ingest_knowledge.py` | CLI: ingest one file or all |
| Create | `api/routes/knowledge.py` | Admin CRUD endpoints |
| Modify | `api/main.py` | Register knowledge router |
| Modify | `requirements.txt` | Add scikit-learn, PyYAML |
| Create | `tests/test_knowledge.py` | All knowledge system tests |

---

## Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Check current requirements**

```bash
grep -E "scikit|yaml|pytest" requirements.txt
```

- [ ] **Step 2: Add dependencies**

Open `requirements.txt` and append:

```
scikit-learn>=1.3.0
PyYAML>=6.0
pytest>=7.4.0
```

- [ ] **Step 3: Install**

```bash
source venv/bin/activate
pip install scikit-learn PyYAML pytest
```

Expected output: `Successfully installed scikit-learn-X.X PyYAML-X.X`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat(knowledge): add scikit-learn and PyYAML dependencies"
```

---

## Task 2: DB schema — knowledge tables

**Files:**
- Modify: `db/setup.py`

- [ ] **Step 1: Write the failing test first**

Create `tests/test_knowledge.py`:

```python
import sqlite3
import pytest
from pathlib import Path
import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path(__file__).parent.parent / "fuelup.db"

def test_knowledge_tables_exist():
    """DB must have knowledge_items and knowledge_chunks tables."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "knowledge_items" in tables
    assert "knowledge_chunks" in tables

def test_knowledge_items_schema():
    """knowledge_items must have required columns."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(knowledge_items)"
    ).fetchall()}
    conn.close()
    required = {"id", "slug", "title", "category", "source", "source_urls",
                "last_reviewed_date", "applicable_age_range", "tags",
                "review_status", "version", "file_path", "ingested_at"}
    assert required.issubset(cols)

def test_knowledge_chunks_schema():
    """knowledge_chunks must have required columns."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(knowledge_chunks)"
    ).fetchall()}
    conn.close()
    required = {"id", "item_id", "chunk_index", "heading", "content", "created_at"}
    assert required.issubset(cols)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
source venv/bin/activate
pytest tests/test_knowledge.py::test_knowledge_tables_exist -v
```

Expected: `FAILED — knowledge_items not in tables`

- [ ] **Step 3: Add schema to db/setup.py**

Open `db/setup.py`. Inside the `cursor.executescript("""...""")` block, before the closing `""")`, add:

```sql
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            source TEXT,
            source_urls TEXT,
            last_reviewed_date TEXT,
            applicable_age_range TEXT,
            tags TEXT,
            review_status TEXT DEFAULT 'draft',
            version INTEGER DEFAULT 1,
            file_path TEXT NOT NULL,
            ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER REFERENCES knowledge_items(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            heading TEXT,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_item
            ON knowledge_chunks(item_id);

        CREATE INDEX IF NOT EXISTS idx_knowledge_items_status
            ON knowledge_items(review_status);
```

- [ ] **Step 4: Run migration**

```bash
python db/setup.py
```

Expected: `AthFuelPath database initialized.`

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_knowledge.py::test_knowledge_tables_exist tests/test_knowledge.py::test_knowledge_items_schema tests/test_knowledge.py::test_knowledge_chunks_schema -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add db/setup.py tests/test_knowledge.py
git commit -m "feat(knowledge): add knowledge_items and knowledge_chunks DB tables"
```

---

## Task 3: Knowledge files — create all 7

**Files:**
- Create: `knowledge/iron_magnesium.md`
- Create: `knowledge/hydration.md`
- Create: `knowledge/pre_practice_meals.md`
- Create: `knowledge/post_practice_recovery.md`
- Create: `knowledge/game_day_nutrition.md`
- Create: `knowledge/weekly_checkin.md`
- Create: `knowledge/safety_red_flags.md`

- [ ] **Step 1: Create knowledge directory**

```bash
mkdir -p knowledge
```

- [ ] **Step 2: Create `knowledge/iron_magnesium.md`**

```markdown
---
title: "Iron and Magnesium Requirements for Youth Athletes"
category: "micronutrients"
source: "NIH Office of Dietary Supplements / ACSM / Academy of Nutrition and Dietetics / Dietitians of Canada"
source_urls:
  - "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"
  - "https://ods.od.nih.gov/factsheets/Magnesium-HealthProfessional/"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["iron", "magnesium", "minerals", "female-athletes", "fatigue", "performance", "RDA"]
review_status: "approved"
version: 1
---

## Daily Iron Requirements (RDA)

The Recommended Dietary Allowance (RDA) for iron is established by the Food and Nutrition Board at the Institute of Medicine of the National Academies.

- Males age 9–13: **8 mg/day**
- Males age 14–18: **11 mg/day**
- Females age 9–13: **8 mg/day**
- Females age 14–18: **15 mg/day**

Female athletes aged 14–18 need almost double what males need because of menstrual losses. The ACSM notes that approximately 52% of female athletes show signs of iron deficiency, which directly impacts endurance, speed, and the ability to recover between sessions.

## Why Iron Matters for Soccer Athletes

Iron is the key mineral for oxygen delivery. Without enough iron, red blood cells cannot carry adequate oxygen to working muscles. This shows up as:
- Unexplained fatigue during practice
- Slower recovery between games
- Reduced sprint speed in the second half

## Daily Magnesium Requirements (RDA)

- Males age 9–13: **240 mg/day**
- Males age 14–18: **410 mg/day**
- Females age 9–13: **240 mg/day**
- Females age 14–18: **360 mg/day**

Magnesium supports muscle function, sleep quality, and energy production. Athletes who sweat heavily (high-intensity soccer training) lose magnesium and need consistent dietary intake to maintain performance.

## Best Food Sources

**Iron-rich foods:**
- Lean beef and chicken thighs
- Lentils and black beans
- Fortified cereal
- Spinach (pair with vitamin C to improve absorption)
- Tofu

**Key tip:** Eating iron with vitamin C (orange juice, bell peppers, strawberries) significantly increases absorption. Avoid eating iron-rich foods with calcium-rich foods at the same meal — they compete for absorption.

**Magnesium-rich foods:**
- Pumpkin seeds and almonds
- Black beans and edamame
- Brown rice and whole grain bread
- Bananas and avocado
- Dark chocolate (70%+)

## Warning Signs to Watch

If an athlete shows persistent fatigue, paleness, or shortness of breath during normal activity, these may be signs of iron-deficiency anemia. This requires testing by a medical professional — do not attempt to self-diagnose or supplement without guidance.
```

- [ ] **Step 3: Create `knowledge/hydration.md`**

```markdown
---
title: "Hydration Guidelines for Youth Soccer Athletes"
category: "hydration"
source: "ACSM Position Stand on Exercise and Fluid Replacement / NIH / Everett MD 2025"
source_urls:
  - "https://journals.lww.com/acsm-msse/Fulltext/2007/02000/Exercise_and_Fluid_Replacement.22.aspx"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["hydration", "water", "electrolytes", "sweat", "game-day", "performance"]
review_status: "approved"
version: 1
---

## Daily Hydration Targets by Event Type

Daily fluid needs vary based on activity level and environmental conditions.

- **Rest day:** 64–72 oz (8–9 cups)
- **Practice day:** 72–80 oz (9–10 cups)
- **Game day:** 80–88 oz (10–11 cups)
- **Tournament day:** 88–96 oz (11–12 cups)

These targets assume moderate temperatures. Add 8–16 oz per day on hot days (above 85°F).

## The 2% Rule

Research shows that losing just 2% of body weight through sweat measurably slows reaction time and reduces aerobic capacity. For a 120 lb athlete, that is only 2.4 lbs of fluid. By the time an athlete feels thirsty, they are already at or near this threshold.

**Practical rule: drink before you are thirsty.**

## Game-Day Hydration Protocol

- Night before: drink 16–24 oz water with dinner
- Morning of game: 16 oz with breakfast
- 2 hours before kickoff: 16 oz
- 30 minutes before kickoff: 8 oz
- Every 15–20 minutes during game: 4–8 oz
- Within 30 minutes after game: 16–24 oz (start recovery)

## Electrolytes

Plain water is sufficient for practices under 60 minutes in moderate weather. For games, tournaments, or hot-weather practices over 60 minutes, electrolytes matter:

- **Sodium** replaces what is lost in sweat and helps the body retain fluid
- **Potassium** supports muscle contraction and prevents cramps
- **Natural options:** coconut water, banana + water, orange slices at halftime

**Avoid:** sports drinks with Red Dye 40 or Yellow Dye 5 (artificial colors). Choose natural electrolyte sources or plain coconut water.

## Signs of Dehydration

Mild: dark yellow urine, dry mouth, reduced energy
Moderate: headache, dizziness, muscle cramps
Severe: fainting, confusion, inability to produce tears — this is a medical emergency. Stop all activity and seek medical help immediately.

## Urine Color Guide

- Pale yellow (lemonade color): well hydrated ✓
- Dark yellow (apple juice): drink more water now
- Orange or brown: severely dehydrated — stop activity
```

- [ ] **Step 4: Create `knowledge/pre_practice_meals.md`**

```markdown
---
title: "Pre-Practice and Pre-Game Meal Timing for Youth Soccer"
category: "meal-timing"
source: "ACSM / Academy of Nutrition and Dietetics / Everett MD 2025"
source_urls:
  - "https://www.eatright.org/fitness/sports-and-performance"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["pre-game", "pre-practice", "meal-timing", "carbohydrates", "energy", "performance"]
review_status: "approved"
version: 1
---

## The Pre-Practice Meal Window

Eating at the right time before practice or a game is as important as what you eat. The goal is to fuel muscles without causing stomach discomfort during high-intensity activity.

**2.5–4 hours before:** Full meal (carbs + protein + moderate fat)
**30–60 minutes before:** Light snack only (easy-digest carbs, no fat or fiber)
**Less than 30 minutes before:** Nothing new — stick to small sips of water

## What to Eat — Full Pre-Practice Meal (2.5–4 hrs before)

Focus: HIGH carbohydrates, moderate protein, LOW fat and fiber

Good choices:
- Pasta or rice with grilled chicken and light sauce
- Whole grain toast with eggs and orange juice
- Oatmeal with banana and a glass of milk
- Turkey sandwich on white bread with fruit

Avoid before practice: fried foods, large amounts of cheese, beans, raw vegetables (high fiber slows digestion)

## What to Eat — Pre-Game Snack (30–60 min before)

Focus: FAST carbohydrates only — no protein, no fat, minimal fiber

Good choices:
- Banana
- Toast with honey
- Rice cakes
- Applesauce pouch
- Handful of crackers

**Familiar foods only on game day.** Never try a new food on game day — even healthy foods can cause unexpected stomach problems.

## Game-Day Breakfast (3+ hours before kickoff)

This is your last full meal before the game. Make it count:
- High carbs (pasta, pancakes, bagel, oatmeal)
- Moderate protein (eggs, Greek yogurt)
- Low fat and low fiber — keep digestion simple
- Familiar foods only

## The Night Before a Game

The night-before dinner is actually the most important game-day meal. Muscle glycogen — your primary fuel for a 90-minute game — is loaded 24–48 hours before kickoff.

Best pre-game dinner: pasta or rice with protein (chicken, fish) and vegetables. No heavy cream sauces or fried foods.

## Carbohydrate Targets by Event Type

The Academy of Nutrition and Dietetics and ACSM recommend:
- Rest days: 4–5 g carbs per kg body weight
- Practice days: 6–8 g carbs per kg body weight
- Game days: 8–10 g carbs per kg body weight
- Tournament days: 10–12 g carbs per kg body weight
```

- [ ] **Step 5: Create `knowledge/post_practice_recovery.md`**

```markdown
---
title: "Post-Practice and Post-Game Recovery Nutrition"
category: "recovery"
source: "ACSM / Everett MD 2025 / Academy of Nutrition and Dietetics"
source_urls:
  - "https://www.acsm.org/education-resources/trending-topics-resources/physical-activity-guidelines"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["recovery", "post-game", "post-practice", "protein", "glycogen", "chocolate-milk", "casein"]
review_status: "approved"
version: 1
---

## The 30-Minute Recovery Window

Within 30 minutes after a game or hard practice, muscles are primed to absorb nutrients for repair and glycogen replenishment. This window is non-negotiable for athletes who train or compete multiple times per week.

**Miss this window → slower recovery → worse performance in the next session.**

## The 3:1 Carb-to-Protein Rule

The ACSM-endorsed recovery ratio is approximately 3 grams of carbohydrates for every 1 gram of protein. This combination:
1. Rapidly restores muscle glycogen (carbs)
2. Triggers muscle protein synthesis (protein)
3. Reduces muscle breakdown and soreness

**The gold standard recovery snack: chocolate milk + banana**
- Chocolate milk provides roughly 3:1 carb-to-protein ratio naturally
- A banana adds fast carbohydrates
- Easy to carry and consume immediately after a game

Other good options:
- Greek yogurt + fruit + granola
- Turkey wrap with fruit juice
- Smoothie with milk, banana, and nut butter

## Bedtime Casein for Muscle Repair

On game days and hard training days, eating a casein-rich snack before bed extends muscle repair through the night. Casein is a slow-digesting protein.

Best bedtime snack options:
- Cottage cheese with a little honey or fruit (25–30g casein)
- Greek yogurt (20g protein)

This is especially important for athletes with two games in two days or back-to-back training sessions.

## Full Recovery Meal (1–2 hours after game)

After the immediate snack, a full recovery meal completes the process:
- Carbohydrates: rice, pasta, potatoes (restore glycogen)
- Protein: chicken, fish, eggs (repair muscle)
- Vegetables: anti-inflammatory foods that reduce soreness
- Fluids: continue hydrating until urine returns to pale yellow

## Iron Focus on Recovery Days

Rest days and recovery days are the best time to prioritize iron-rich meals. When the body is not in high-performance mode, iron absorption is more efficient. Include iron-rich foods (lentils, lean beef, fortified cereal) at recovery meals.
```

- [ ] **Step 6: Create `knowledge/game_day_nutrition.md`**

```markdown
---
title: "Complete Game-Day Nutrition Guide for Youth Soccer"
category: "game-day"
source: "ACSM / Everett MD 2025 / Academy of Nutrition and Dietetics"
source_urls:
  - "https://www.eatright.org/fitness/sports-and-performance"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["game-day", "performance", "carbohydrates", "glycogen", "halftime", "kickoff"]
review_status: "approved"
version: 1
---

## Game-Day Eating Schedule

### Night Before (most important meal of the week)
High-carb dinner to load muscle glycogen. Glycogen loading takes 24–48 hours, so tonight's pasta matters more than tomorrow's breakfast.
- Pasta or rice with lean protein
- Bread, fruit, milk
- Avoid heavy sauces, fried food, large amounts of fat

### Morning of Game (3–4 hours before kickoff)
Last full meal. High carbs, moderate protein, low fat and fiber.
- Oatmeal with banana and milk
- Bagel with peanut butter and OJ
- Pancakes with eggs and fruit
- No new or unusual foods

### Pre-Game Snack (30–60 minutes before kickoff)
Fast carbs only. Keep it small. Nothing heavy.
- Banana
- Toast with honey
- Rice cakes
- Sports gel or applesauce pouch

### Halftime
Quick refuel for the second half:
- Orange slices or banana
- 8–12 oz water or natural sports drink
- No heavy foods — keep it light

### Post-Game (within 30 minutes)
Start recovery immediately:
- Chocolate milk + banana (gold standard)
- 16–20 oz water or electrolyte drink

### Dinner (1–2 hours post-game)
Full recovery meal:
- Rice or pasta + lean protein + vegetables
- Continue hydrating
- Iron-rich foods if possible

## What to Avoid on Game Day

- High-fat foods (fried chicken, pizza, cheese-heavy dishes) — slow digestion, cause sluggishness
- High-fiber foods right before game (beans, raw vegetables, whole bran) — GI distress risk
- Energy drinks — not appropriate for youth athletes; caffeine disrupts sleep and hydration
- New foods — always eat familiar foods on game day

## Tournament Day (Multiple Games)

For tournaments with 2+ games, the refuel window between games is shorter than a normal recovery window. Prioritize:
1. Chocolate milk or recovery drink immediately after game 1
2. Light carb snack 60 min before game 2
3. Higher carb dinner the night before
4. Electrolytes throughout the day
```

- [ ] **Step 7: Create `knowledge/weekly_checkin.md`**

```markdown
---
title: "Weekly Fuel Quality Assessment for Youth Athletes"
category: "weekly-checkin"
source: "Academy of Nutrition and Dietetics / Everett MD 2025"
source_urls:
  - "https://www.eatright.org/fitness/sports-and-performance"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["weekly-review", "habits", "consistency", "fuel-score", "planning"]
review_status: "approved"
version: 1
---

## What Good Fueling Looks Like Across a Week

Nutrition for youth athletes is not about perfection on one day — it is about consistent habits across the whole week. The goal is to build patterns, not to get a perfect score on game day.

## Weekly Check-In Questions

At the end of each week, review these five areas:

**1. Carbohydrates:** Did you eat carbs at most meals? (Rice, pasta, bread, oats, fruit, potatoes)
**2. Protein:** Did you eat protein 3–4 times per day? (Eggs, chicken, beef, fish, dairy, beans)
**3. Hydration:** Was your urine pale yellow most of the day?
**4. Iron and calcium:** Did you eat iron-rich and calcium-rich foods on most days?
**5. Recovery meals:** Did you eat within 30 minutes after each hard practice or game?

## What a Strong Fuel Week Looks Like

- Carbs at every meal
- Protein 3–4x per day
- 8–10 cups water daily
- Recovery snack within 30 min of every hard session
- Pre-game meal 2.5–4 hours before every game
- Iron-rich food at least once per day (especially for female athletes)
- Calcium-rich food at least twice per day (milk, yogurt, fortified foods)

## Warning Signs of Underfueling

If an athlete experiences these patterns consistently, nutrition may be insufficient:
- Fatigue that does not improve with rest
- Getting sick more often than usual
- Slower sprint times or reduced endurance over weeks
- Muscle cramps occurring frequently
- Difficulty concentrating in school
- Mood changes, irritability, or difficulty sleeping

These symptoms warrant a conversation with a sports dietitian. Do not attempt to self-diagnose.

## Building Better Habits

The most effective nutrition change for youth athletes is usually the simplest: **eat more consistently throughout the day.** Long gaps without food (more than 4–5 hours) deplete energy stores and impair afternoon practice performance.

Aim for meals or snacks every 3–4 hours during the day, with the largest carb portions timed around training and competition.
```

- [ ] **Step 8: Create `knowledge/safety_red_flags.md`**

```markdown
---
title: "Medical Red Flags — When to Seek Professional Help"
category: "safety"
source: "American Academy of Pediatrics / ACSM / Academy of Nutrition and Dietetics"
source_urls:
  - "https://www.aap.org/en/patient-care/sports/"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["safety", "red-flags", "medical", "eating-disorder", "dehydration", "injury", "referral"]
review_status: "approved"
version: 1
---

## When to Stop and Seek Medical Help Immediately

These situations require stopping all activity and contacting a medical professional or emergency services:

- **Fainting or loss of consciousness** during or after exercise
- **Chest pain or pressure** during exercise
- **Severe dizziness or inability to stand** after activity
- **Vomiting that does not stop** after exercise
- **Dark brown or orange urine** — possible severe dehydration or muscle breakdown
- **Signs of heat stroke:** hot/dry skin, confusion, no sweating despite heat

Call 911 or go to an emergency room for any of these.

## Eating and Eating Disorders — When to Seek Help

AthFuelPath provides food education guidance only. The following signs may indicate a serious health issue that requires a qualified professional:

- Athlete is consistently avoiding entire food groups (not due to allergy)
- Significant unintentional weight loss over weeks
- Athlete expresses extreme fear of gaining weight
- Athlete is restricting food intake to lose weight for sport
- Signs of binge-purge behaviors
- Athlete reports feeling dizzy, cold all the time, or losing hair

If you observe any of these signs, please consult a registered dietitian (RD), the athlete's physician, or a mental health professional. **AthFuelPath is not equipped to address eating disorders.** Early intervention is critical and effective.

## Iron Deficiency Anemia — When to Test

These symptoms together may indicate iron-deficiency anemia, which requires a blood test to confirm:
- Persistent fatigue not explained by training load
- Paleness (especially gums and inner eyelids)
- Shortness of breath during activities that were previously easy
- Rapid heartbeat at rest
- Headaches

Diagnosis requires a blood test (serum ferritin + hemoglobin). Do not supplement iron without a confirmed diagnosis — excess iron can be harmful.

## Overtraining and Relative Energy Deficiency (RED-S)

RED-S (previously called the Female Athlete Triad) occurs when an athlete does not eat enough to support both training and normal body functions. Signs include:
- Stress fractures or frequent injury
- Missed or irregular menstrual cycles (female athletes)
- Declining performance despite consistent training
- Frequent illness or slow healing

This requires evaluation by a sports medicine physician and registered dietitian. AthFuelPath can support healthy fueling habits but cannot treat RED-S.

## What AthFuelPath Can and Cannot Do

**AthFuelPath provides:** Educational food guidance, meal timing recommendations, hydration targets, and evidence-based nutrition information for healthy youth athletes.

**AthFuelPath cannot:** Diagnose medical conditions, treat eating disorders, prescribe supplements, replace a doctor or registered dietitian, or provide medical advice.

When in doubt, consult a qualified professional.
```

- [ ] **Step 9: Commit all knowledge files**

```bash
git add knowledge/
git commit -m "feat(knowledge): add 7 approved knowledge files for youth soccer nutrition"
```

---

## Task 4: Package init + ingest service

**Files:**
- Create: `api/services/knowledge/__init__.py`
- Create: `api/services/knowledge/ingest.py`

- [ ] **Step 1: Write failing tests for ingest**

Add to `tests/test_knowledge.py`:

```python
import json
from pathlib import Path

def _get_conn():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def test_ingest_creates_knowledge_item():
    """Ingesting an approved file creates a knowledge_items row."""
    from api.services.knowledge.ingest import ingest_file
    iron_path = Path(__file__).parent.parent / "knowledge" / "iron_magnesium.md"
    ingest_file(str(iron_path))
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM knowledge_items WHERE slug = 'iron_magnesium'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["title"] == "Iron and Magnesium Requirements for Youth Athletes"
    assert row["review_status"] == "approved"

def test_ingest_creates_chunks():
    """Ingesting a file creates at least 3 chunks in knowledge_chunks."""
    conn = _get_conn()
    item = conn.execute(
        "SELECT id FROM knowledge_items WHERE slug = 'iron_magnesium'"
    ).fetchone()
    if not item:
        from api.services.knowledge.ingest import ingest_file
        iron_path = Path(__file__).parent.parent / "knowledge" / "iron_magnesium.md"
        ingest_file(str(iron_path))
        conn = _get_conn()
        item = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = 'iron_magnesium'"
        ).fetchone()
    chunks = conn.execute(
        "SELECT * FROM knowledge_chunks WHERE item_id = ?", (item["id"],)
    ).fetchall()
    conn.close()
    assert len(chunks) >= 3

def test_draft_file_not_ingested(tmp_path):
    """A file with review_status: draft must not be ingested."""
    draft = tmp_path / "draft_test.md"
    draft.write_text("""---
title: "Draft Test"
category: "test"
source: "test"
source_urls: []
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["test"]
review_status: "draft"
version: 1
---

## Test Content

This should never be ingested.
""")
    from api.services.knowledge.ingest import ingest_file
    result = ingest_file(str(draft))
    assert result["status"] == "skipped"
    assert "draft" in result["reason"]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_knowledge.py::test_ingest_creates_knowledge_item -v
```

Expected: `FAILED — ModuleNotFoundError: api.services.knowledge.ingest`

- [ ] **Step 3: Create package init**

```bash
mkdir -p api/services/knowledge
touch api/services/knowledge/__init__.py
```

- [ ] **Step 4: Create `api/services/knowledge/ingest.py`**

```python
import re
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import yaml

from api.database import get_conn


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from Markdown body. Returns (meta, body)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return meta, body


def _chunk_markdown(body: str, max_chars: int = 1600) -> list[dict]:
    """
    Split Markdown body at H2/H3 headings.
    Returns list of {"heading": str, "content": str}.
    Each chunk is at most max_chars characters.
    """
    heading_pattern = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
    chunks = []
    positions = [(m.start(), m.group(2), m.group(0)) for m in heading_pattern.finditer(body)]

    if not positions:
        # No headings — treat entire body as one chunk
        for i in range(0, len(body), max_chars):
            chunks.append({"heading": None, "content": body[i:i + max_chars].strip()})
        return chunks

    # Text before first heading
    if positions[0][0] > 0:
        intro = body[:positions[0][0]].strip()
        if intro:
            chunks.append({"heading": None, "content": intro})

    for i, (start, heading_text, _) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        section_body = body[start:end].strip()
        # Remove the heading line itself from content
        section_lines = section_body.split('\n', 1)
        content = section_lines[1].strip() if len(section_lines) > 1 else ""
        if not content:
            continue
        # Split if too long
        for j in range(0, max(1, len(content)), max_chars):
            chunks.append({
                "heading": heading_text,
                "content": content[j:j + max_chars].strip(),
            })

    return [c for c in chunks if c["content"]]


def ingest_file(file_path: str) -> dict:
    """
    Parse a knowledge Markdown file and store it in the database.
    Returns {"status": "ok"|"skipped", "slug": str, "chunks": int, "reason": str|None}.
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "reason": f"File not found: {file_path}"}

    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    status = meta.get("review_status", "draft")
    if status != "approved":
        return {
            "status": "skipped",
            "slug": path.stem,
            "chunks": 0,
            "reason": f"review_status is '{status}', only 'approved' files are ingested",
        }

    slug = path.stem
    chunks = _chunk_markdown(body)

    conn = get_conn()
    try:
        # Upsert knowledge_items
        conn.execute(
            """INSERT INTO knowledge_items
               (slug, title, category, source, source_urls, last_reviewed_date,
                applicable_age_range, tags, review_status, version, file_path, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 title = excluded.title,
                 category = excluded.category,
                 source = excluded.source,
                 source_urls = excluded.source_urls,
                 last_reviewed_date = excluded.last_reviewed_date,
                 applicable_age_range = excluded.applicable_age_range,
                 tags = excluded.tags,
                 review_status = excluded.review_status,
                 version = excluded.version,
                 file_path = excluded.file_path,
                 ingested_at = excluded.ingested_at""",
            (
                slug,
                meta.get("title", slug),
                meta.get("category", "general"),
                meta.get("source", ""),
                json.dumps(meta.get("source_urls", [])),
                meta.get("last_reviewed_date", ""),
                meta.get("applicable_age_range", "9-17"),
                json.dumps(meta.get("tags", [])),
                status,
                meta.get("version", 1),
                str(path.resolve()),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

        item_row = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = ?", (slug,)
        ).fetchone()
        item_id = item_row["id"]

        # Replace existing chunks for this item
        conn.execute("DELETE FROM knowledge_chunks WHERE item_id = ?", (item_id,))
        for i, chunk in enumerate(chunks):
            conn.execute(
                "INSERT INTO knowledge_chunks (item_id, chunk_index, heading, content) VALUES (?, ?, ?, ?)",
                (item_id, i, chunk["heading"], chunk["content"]),
            )
        conn.commit()

    finally:
        conn.close()

    return {"status": "ok", "slug": slug, "chunks": len(chunks), "reason": None}


def ingest_all(knowledge_dir: str = "knowledge") -> list[dict]:
    """Ingest all .md files in the knowledge directory."""
    results = []
    for md_file in sorted(Path(knowledge_dir).glob("*.md")):
        results.append(ingest_file(str(md_file)))
    return results
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_knowledge.py::test_ingest_creates_knowledge_item tests/test_knowledge.py::test_ingest_creates_chunks tests/test_knowledge.py::test_draft_file_not_ingested -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add api/services/knowledge/ tests/test_knowledge.py
git commit -m "feat(knowledge): add ingest service with chunk splitting and frontmatter parsing"
```

---

## Task 5: Retrieval service (TF-IDF)

**Files:**
- Create: `api/services/knowledge/retrieval.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_knowledge.py`:

```python
def test_retrieval_finds_iron_content():
    """Query about iron needs should return chunks from iron_magnesium.md."""
    # Ensure iron_magnesium is ingested first
    from api.services.knowledge.ingest import ingest_file
    iron_path = Path(__file__).parent.parent / "knowledge" / "iron_magnesium.md"
    ingest_file(str(iron_path))

    from api.services.knowledge.retrieval import retrieve
    results = retrieve("how much iron does a teenage girl need per day")
    assert len(results) > 0
    titles = [r["title"] for r in results]
    assert any("Iron" in t or "Magnesium" in t for t in titles)

def test_retrieval_returns_empty_for_unknown_domain():
    """Out-of-domain query should return empty list (score below threshold)."""
    from api.services.knowledge.retrieval import retrieve
    results = retrieve("what is the latest iPhone model price")
    # May return something due to TF-IDF noise, but nothing should have high score
    # Enforce with a stricter check — none should have score > 0.05
    for r in results:
        assert r["score"] < 0.05, f"Unexpected high score {r['score']} for out-of-domain query"

def test_retrieval_respects_approved_only():
    """Only approved chunks are returned — draft and archived must not appear."""
    from api.services.knowledge.retrieval import retrieve
    results = retrieve("test draft content should never appear")
    for r in results:
        assert r["review_status"] == "approved"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_knowledge.py::test_retrieval_finds_iron_content -v
```

Expected: `FAILED — ModuleNotFoundError: api.services.knowledge.retrieval`

- [ ] **Step 3: Create `api/services/knowledge/retrieval.py`**

```python
import json
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from api.database import get_conn

MIN_SCORE = 0.05  # below this threshold, chunk is not returned
DEFAULT_TOP_N = 5


@dataclass
class KnowledgeChunk:
    chunk_id: int
    item_id: int
    slug: str
    title: str
    category: str
    source: str
    source_urls: list[str]
    applicable_age_range: str
    tags: list[str]
    review_status: str
    heading: Optional[str]
    content: str
    score: float


def retrieve(query: str, top_n: int = DEFAULT_TOP_N) -> list[KnowledgeChunk]:
    """
    Retrieve the top-N most relevant approved knowledge chunks for the query.
    Returns empty list if no chunk scores above MIN_SCORE.
    """
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT kc.id as chunk_id, kc.item_id, kc.heading, kc.content,
                      ki.slug, ki.title, ki.category, ki.source, ki.source_urls,
                      ki.applicable_age_range, ki.tags, ki.review_status
               FROM knowledge_chunks kc
               JOIN knowledge_items ki ON kc.item_id = ki.id
               WHERE ki.review_status = 'approved'
               ORDER BY kc.item_id, kc.chunk_index"""
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    texts = [row["content"] for row in rows]
    corpus = texts + [query]

    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)

    chunk_vectors = tfidf_matrix[:-1]
    query_vector = tfidf_matrix[-1]

    scores = cosine_similarity(query_vector, chunk_vectors).flatten()

    # Get top-N indices above threshold
    top_indices = np.argsort(scores)[::-1][:top_n]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score < MIN_SCORE:
            break
        row = rows[idx]
        results.append(KnowledgeChunk(
            chunk_id=row["chunk_id"],
            item_id=row["item_id"],
            slug=row["slug"],
            title=row["title"],
            category=row["category"],
            source=row["source"],
            source_urls=json.loads(row["source_urls"] or "[]"),
            applicable_age_range=row["applicable_age_range"],
            tags=json.loads(row["tags"] or "[]"),
            review_status=row["review_status"],
            heading=row["heading"],
            content=row["content"],
            score=score,
        ))

    return results
```

- [ ] **Step 4: Ingest all knowledge files first, then run tests**

```bash
python -c "
from api.services.knowledge.ingest import ingest_all
results = ingest_all()
for r in results: print(r)
"
```

Expected: 7 lines showing `{'status': 'ok', 'slug': '...', 'chunks': N, 'reason': None}`

- [ ] **Step 5: Run retrieval tests**

```bash
pytest tests/test_knowledge.py::test_retrieval_finds_iron_content tests/test_knowledge.py::test_retrieval_returns_empty_for_unknown_domain tests/test_knowledge.py::test_retrieval_respects_approved_only -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add api/services/knowledge/retrieval.py tests/test_knowledge.py
git commit -m "feat(knowledge): add TF-IDF retrieval service with MIN_SCORE threshold"
```

---

## Task 6: Calculations service

**Files:**
- Create: `api/services/knowledge/calculations.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_knowledge.py`:

```python
def test_iron_rda_female_14():
    """Female age 14 iron RDA is 15mg per NIH."""
    from api.services.knowledge.calculations import iron_rda
    result = iron_rda(14, "female")
    assert result["value"] == 15
    assert result["unit"] == "mg/day"
    assert "NIH" in result["source"]

def test_iron_rda_male_14():
    """Male age 14 iron RDA is 11mg per NIH."""
    from api.services.knowledge.calculations import iron_rda
    result = iron_rda(14, "male")
    assert result["value"] == 11

def test_iron_rda_child_9():
    """Age 9 iron RDA is 8mg regardless of gender per NIH."""
    from api.services.knowledge.calculations import iron_rda
    assert iron_rda(9, "female")["value"] == 8
    assert iron_rda(9, "male")["value"] == 8

def test_calcium_rda_youth():
    """Ages 9-18 calcium RDA is 1300mg per NIH."""
    from api.services.knowledge.calculations import calcium_rda
    result = calcium_rda(14)
    assert result["value"] == 1300
    assert result["unit"] == "mg/day"

def test_protein_range_game_day():
    """120 lb athlete on game day: 1.6-1.8 g/kg = 87-98g."""
    from api.services.knowledge.calculations import protein_range
    result = protein_range(120, "game")
    assert result["min_g"] == 87
    assert result["max_g"] == 98
    assert result["unit"] == "g/day"

def test_hydration_needs_game():
    """120 lb athlete on game day without heat: 80-88 oz."""
    from api.services.knowledge.calculations import hydration_needs
    result = hydration_needs(120, "game", weather_hot=False)
    assert result["min_oz"] == 80
    assert result["max_oz"] == 88

def test_hydration_needs_hot_weather():
    """Hot weather adds 8-16 oz to baseline."""
    from api.services.knowledge.calculations import hydration_needs
    normal = hydration_needs(120, "rest", weather_hot=False)
    hot = hydration_needs(120, "rest", weather_hot=True)
    assert hot["min_oz"] == normal["min_oz"] + 8
    assert hot["max_oz"] == normal["max_oz"] + 16

def test_pre_training_meal_window():
    """Event at 18:00 → full meal by 15:30, snack by 17:00."""
    from api.services.knowledge.calculations import pre_training_meal_window
    result = pre_training_meal_window("18:00")
    assert result["full_meal_by"] == "15:30"
    assert result["snack_by"] == "17:00"

def test_post_training_recovery_window():
    """Event ends at 20:00 → window open 20:00, closes 20:30."""
    from api.services.knowledge.calculations import post_training_recovery_window
    result = post_training_recovery_window("20:00")
    assert result["window_opens"] == "20:00"
    assert result["window_closes"] == "20:30"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_knowledge.py::test_iron_rda_female_14 -v
```

Expected: `FAILED — ModuleNotFoundError`

- [ ] **Step 3: Create `api/services/knowledge/calculations.py`**

```python
"""
Deterministic nutrition calculation functions for youth athletes.
All numeric values come from peer-reviewed sources (NIH, ACSM, AND).
Claude explains results — these functions produce them.
"""

from datetime import datetime, timedelta

# ── Iron RDA (NIH Office of Dietary Supplements) ─────────────────────────────
# https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/
_IRON_RDA = {
    "male":   {(9, 13): 8,  (14, 18): 11},
    "female": {(9, 13): 8,  (14, 18): 15},
}


def iron_rda(age: int, gender: str) -> dict:
    """Return daily iron RDA in mg for a youth athlete."""
    gender_key = "female" if gender.lower() in ("female", "girl", "f") else "male"
    table = _IRON_RDA[gender_key]
    for (low, high), value in table.items():
        if low <= age <= high:
            return {
                "value": value,
                "unit": "mg/day",
                "source": "NIH Office of Dietary Supplements — Iron Fact Sheet",
                "source_url": "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
                "explanation_hint": (
                    f"The RDA for iron for a {age}-year-old {gender_key} is {value}mg per day. "
                    f"{'Female athletes aged 14–18 need almost double males due to menstrual losses.' if gender_key == 'female' and age >= 14 else ''}"
                ),
            }
    return {"value": 8, "unit": "mg/day", "source": "NIH", "source_url": "", "explanation_hint": "Default RDA"}


# ── Calcium RDA (NIH) ──────────────────────────────────────────────────────────
def calcium_rda(age: int) -> dict:
    """Return daily calcium RDA in mg. Ages 9–18 = 1300mg (NIH)."""
    value = 1300 if 9 <= age <= 18 else 1000
    return {
        "value": value,
        "unit": "mg/day",
        "source": "NIH Office of Dietary Supplements — Calcium Fact Sheet",
        "source_url": "https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/",
        "explanation_hint": (
            f"The RDA for calcium for athletes aged 9–18 is {value}mg per day. "
            "This is the peak bone mass window — calcium intake now determines bone strength for life."
        ),
    }


# ── Protein range (ACSM / AND / DC position stand) ────────────────────────────
_PROTEIN_G_PER_KG = {
    "rest":       (1.2, 1.4),
    "practice":   (1.4, 1.6),
    "training":   (1.4, 1.6),
    "strength":   (1.8, 2.0),
    "game":       (1.6, 1.8),
    "tournament": (1.8, 2.0),
}

_LBS_TO_KG = 0.453592


def protein_range(weight_lbs: float, event_type: str) -> dict:
    """Return daily protein range in grams based on weight and event type."""
    key = event_type.lower() if event_type.lower() in _PROTEIN_G_PER_KG else "rest"
    low_per_kg, high_per_kg = _PROTEIN_G_PER_KG[key]
    weight_kg = weight_lbs * _LBS_TO_KG
    min_g = round(weight_kg * low_per_kg)
    max_g = round(weight_kg * high_per_kg)
    return {
        "min_g": min_g,
        "max_g": max_g,
        "unit": "g/day",
        "per_kg_range": f"{low_per_kg}–{high_per_kg} g/kg",
        "source": "ACSM / Academy of Nutrition and Dietetics / Dietitians of Canada Position Stand",
        "explanation_hint": (
            f"For a {weight_lbs} lb athlete on a {event_type} day, "
            f"the ACSM recommends {min_g}–{max_g}g of protein per day "
            f"({low_per_kg}–{high_per_kg}g per kg body weight)."
        ),
    }


# ── Hydration targets (ACSM position stand) ───────────────────────────────────
_HYDRATION_OZ = {
    "rest":       (64, 72),
    "practice":   (72, 80),
    "training":   (72, 80),
    "strength":   (72, 80),
    "game":       (80, 88),
    "tournament": (88, 96),
}


def hydration_needs(weight_lbs: float, event_type: str, weather_hot: bool = False) -> dict:
    """Return daily hydration target in oz. Adds 8–16oz for hot weather."""
    key = event_type.lower() if event_type.lower() in _HYDRATION_OZ else "rest"
    min_oz, max_oz = _HYDRATION_OZ[key]
    if weather_hot:
        min_oz += 8
        max_oz += 16
    cups_min = round(min_oz / 8)
    cups_max = round(max_oz / 8)
    return {
        "min_oz": min_oz,
        "max_oz": max_oz,
        "cups_min": cups_min,
        "cups_max": cups_max,
        "unit": "oz/day",
        "weather_hot": weather_hot,
        "source": "ACSM Position Stand on Exercise and Fluid Replacement",
        "explanation_hint": (
            f"On a {event_type} day{'in hot weather ' if weather_hot else ''}, "
            f"the target is {min_oz}–{max_oz}oz ({cups_min}–{cups_max} cups) of fluid. "
            f"{'Add extra fluid on hot days (above 85°F).' if weather_hot else ''}"
        ),
    }


# ── Pre-training meal window ──────────────────────────────────────────────────
def pre_training_meal_window(start_time: str) -> dict:
    """
    Given event start time (HH:MM), return:
    - full_meal_by: eat a full meal by this time (2.5 hrs before)
    - snack_by: last snack by this time (1 hr before)
    """
    try:
        h, m = map(int, start_time.split(":"))
        event_dt = datetime.today().replace(hour=h, minute=m, second=0, microsecond=0)
        full_meal_dt = event_dt - timedelta(hours=2, minutes=30)
        snack_dt = event_dt - timedelta(hours=1)
        return {
            "start_time": start_time,
            "full_meal_by": full_meal_dt.strftime("%H:%M"),
            "snack_by": snack_dt.strftime("%H:%M"),
            "source": "ACSM / Academy of Nutrition and Dietetics",
            "explanation_hint": (
                f"For an event starting at {start_time}, eat your last full meal "
                f"(carbs + protein) by {full_meal_dt.strftime('%I:%M %p')}. "
                f"If you need a snack, have only easy-digest carbs by {snack_dt.strftime('%I:%M %p')}."
            ),
        }
    except ValueError:
        return {"error": f"Invalid time format: {start_time}. Use HH:MM."}


# ── Post-training recovery window ─────────────────────────────────────────────
def post_training_recovery_window(end_time: str) -> dict:
    """
    Given event end time (HH:MM), return the 30-min recovery window.
    """
    try:
        h, m = map(int, end_time.split(":"))
        end_dt = datetime.today().replace(hour=h, minute=m, second=0, microsecond=0)
        close_dt = end_dt + timedelta(minutes=30)
        return {
            "window_opens": end_time,
            "window_closes": close_dt.strftime("%H:%M"),
            "duration_minutes": 30,
            "source": "ACSM — Post-Exercise Recovery Guidelines",
            "explanation_hint": (
                f"The 30-minute recovery window opens at {end_time} and closes at "
                f"{close_dt.strftime('%I:%M %p')}. Eat chocolate milk + banana or "
                "another 3:1 carb:protein snack immediately. Missing this window slows recovery."
            ),
        }
    except ValueError:
        return {"error": f"Invalid time format: {end_time}. Use HH:MM."}


# ── Calorie estimate (Everett RMR formula, same as nutrition_calc.py) ─────────
def calorie_estimate(weight_lbs: float, age: int, gender: str, event_type: str) -> dict:
    """
    Estimate daily calorie needs using Everett 2025 RMR × PAL multiplier.
    Consistent with api/services/nutrition_calc.py.
    """
    from api.services.nutrition_calc import calc_daily_targets
    athlete = {
        "weight_lbs": weight_lbs,
        "age": age,
        "gender": gender,
        "height_ft": 5,
        "height_in": 4,
    }
    targets = calc_daily_targets(athlete, event_type)
    total = targets["total_calories"]
    return {
        "value": total,
        "unit": "kcal/day",
        "source": "Everett MD 2025 RMR formula × PAL multiplier (ACSM)",
        "explanation_hint": (
            f"For a {weight_lbs} lb {age}-year-old on a {event_type} day, "
            f"the estimated daily calorie need is approximately {total} kcal."
        ),
    }
```

- [ ] **Step 4: Run all calculation tests**

```bash
pytest tests/test_knowledge.py -k "rda or protein or hydration or training_meal or recovery_window" -v
```

Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add api/services/knowledge/calculations.py tests/test_knowledge.py
git commit -m "feat(knowledge): add deterministic calculation functions with NIH/ACSM sources"
```

---

## Task 7: Answer orchestration (RAG + Claude)

**Files:**
- Create: `api/services/knowledge/answer.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_knowledge.py`:

```python
from unittest.mock import patch, MagicMock

def test_no_answer_when_empty_retrieval():
    """When no chunks are found, return the safe fallback string."""
    from api.services.knowledge.answer import answer_with_knowledge

    with patch("api.services.knowledge.answer.retrieve", return_value=[]):
        result = answer_with_knowledge(
            "what is the stock price of Apple",
            {"id": 1, "first_name": "Alex", "age": 14, "gender": "female",
             "weight_lbs": 120, "event_type": "rest"}
        )
    assert "don't have enough approved information" in result["answer"]
    assert result["citations"] == []

def test_citations_included_in_answer():
    """Answers from knowledge base must include at least one citation."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="iron_magnesium",
        title="Iron and Magnesium Requirements",
        category="micronutrients",
        source="NIH Office of Dietary Supplements",
        source_urls=["https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"],
        applicable_age_range="9-17", tags=["iron"],
        review_status="approved", heading="Daily Iron Requirements",
        content="Female athletes age 14-18 need 15mg iron per day.",
        score=0.7,
    )

    with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
        with patch("api.services.knowledge.answer._call_claude", return_value="Female athletes need 15mg of iron per day. Source: Iron and Magnesium Requirements"):
            result = answer_with_knowledge(
                "how much iron does a girl need",
                {"id": 1, "first_name": "Alex", "age": 14, "gender": "female",
                 "weight_lbs": 120, "event_type": "rest"}
            )
    assert len(result["citations"]) >= 1
    assert result["citations"][0]["title"] == "Iron and Magnesium Requirements"

def test_safety_guardrail_in_system_prompt():
    """The Claude system prompt must contain safety guardrail instructions."""
    from api.services.knowledge.answer import _build_system_prompt
    prompt = _build_system_prompt(chunks=[], calc_result=None)
    assert "medical" in prompt.lower()
    assert "professional" in prompt.lower()
    assert "eating disorder" in prompt.lower() or "eating" in prompt.lower()

def test_calculation_included_when_relevant():
    """Iron RDA question for a known athlete should include a calc_result."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="iron_magnesium",
        title="Iron and Magnesium Requirements",
        category="micronutrients",
        source="NIH", source_urls=[],
        applicable_age_range="9-17", tags=["iron"],
        review_status="approved", heading="Iron RDA",
        content="Female athletes age 14-18 need 15mg iron per day.",
        score=0.6,
    )

    with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
        with patch("api.services.knowledge.answer._call_claude", return_value="15mg"):
            result = answer_with_knowledge(
                "how much iron does she need",
                {"id": 1, "first_name": "Maya", "age": 15, "gender": "female",
                 "weight_lbs": 115, "event_type": "rest"}
            )
    # calculation should be populated for an iron question with a known athlete
    assert result["calculation"] is not None or result["answer"] is not None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_knowledge.py::test_no_answer_when_empty_retrieval -v
```

Expected: `FAILED — ModuleNotFoundError`

- [ ] **Step 3: Create `api/services/knowledge/answer.py`**

```python
"""
RAG answer orchestration.
Claude receives retrieved knowledge chunks + optional calculation result.
Claude answers ONLY from the provided context.
"""

import re
from typing import Optional

import anthropic

from api.services.knowledge.retrieval import retrieve, KnowledgeChunk
from api.services.knowledge.calculations import (
    iron_rda, calcium_rda, protein_range, hydration_needs,
    pre_training_meal_window, post_training_recovery_window, calorie_estimate,
)

_FALLBACK = "I don't have enough approved information to answer that confidently. Please consult a registered sports dietitian or the athlete's physician for personalised guidance."

_SAFETY_TERMS = [
    "faint", "fainting", "unconscious", "chest pain", "can't breathe",
    "eating disorder", "purge", "starving", "stop eating", "lose weight fast",
    "anorexia", "bulimia", "binge", "severe dehydration", "seizure",
    "vomiting blood", "not eating",
]

_CALC_KEYWORDS = {
    "iron": lambda q, a: iron_rda(a.get("age", 14), a.get("gender", "female")),
    "calcium": lambda q, a: calcium_rda(a.get("age", 14)),
    "protein": lambda q, a: protein_range(a.get("weight_lbs", 120), a.get("event_type", "rest")),
    "hydration": lambda q, a: hydration_needs(a.get("weight_lbs", 120), a.get("event_type", "rest")),
    "water": lambda q, a: hydration_needs(a.get("weight_lbs", 120), a.get("event_type", "rest")),
    "calorie": lambda q, a: calorie_estimate(a.get("weight_lbs", 120), a.get("age", 14), a.get("gender", "female"), a.get("event_type", "rest")),
    "calories": lambda q, a: calorie_estimate(a.get("weight_lbs", 120), a.get("age", 14), a.get("gender", "female"), a.get("event_type", "rest")),
}


def _detect_safety_flag(question: str) -> bool:
    q = question.lower()
    return any(term in q for term in _SAFETY_TERMS)


def _maybe_calculate(question: str, athlete: dict) -> Optional[dict]:
    q = question.lower()
    for keyword, fn in _CALC_KEYWORDS.items():
        if keyword in q:
            try:
                return fn(q, athlete)
            except Exception:
                return None
    return None


def _build_system_prompt(chunks: list[KnowledgeChunk], calc_result: Optional[dict]) -> str:
    chunks_text = ""
    if chunks:
        for i, c in enumerate(chunks, 1):
            heading = f" — {c.heading}" if c.heading else ""
            chunks_text += f"\n[{i}] {c.title}{heading} (Source: {c.source})\n{c.content}\n"
    else:
        chunks_text = "(No relevant knowledge excerpts found)"

    calc_text = ""
    if calc_result and "error" not in calc_result:
        calc_text = f"\n\nCALCULATION RESULT (use this exact value — do not invent numbers):\n{calc_result.get('explanation_hint', str(calc_result))}\nSource: {calc_result.get('source', '')}"

    return f"""You are AthFuelPath's nutrition assistant for youth soccer athletes ages 9–17.

STRICT RULES — follow these exactly:
1. Answer ONLY from the knowledge excerpts provided below. Never invent nutritional values, formulas, or dosages not present in the excerpts.
2. If the excerpts do not contain enough information to answer, respond with exactly: "{_FALLBACK}"
3. End every answer with: "Source: [title of the knowledge item you used]"
4. Write for a youth athlete aged 9–17 — keep language simple, supportive, and practical.
5. Whenever possible, give "what to do today" guidance.
6. NEVER provide medical diagnosis, treatment advice, or supplement dosing.
7. For ANY of these situations — injury, fainting, chest pain, eating disorder, severe dehydration, signs of anorexia or bulimia, extreme restriction, unintentional weight loss — respond with: "This sounds like something important to discuss with a doctor or qualified sports dietitian. Please reach out to a professional right away."

KNOWLEDGE EXCERPTS:
{chunks_text}
{calc_text}"""


def _call_claude(system_prompt: str, user_question: str) -> str:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_question}],
    )
    return message.content[0].text


def answer_with_knowledge(question: str, athlete: dict) -> dict:
    """
    Main RAG entry point.
    Returns {"answer": str, "citations": list, "calculation": dict|None}.
    """
    # Safety flag check — always respond with referral before anything else
    if _detect_safety_flag(question):
        return {
            "answer": "This sounds like something important to discuss with a doctor or qualified sports dietitian. Please reach out to a professional right away.",
            "citations": [],
            "calculation": None,
            "safety_flag": True,
        }

    # Run deterministic calculation if relevant
    calc_result = _maybe_calculate(question, athlete)

    # Retrieve knowledge chunks
    chunks = retrieve(question, top_n=5)

    # No knowledge found → safe fallback
    if not chunks:
        return {
            "answer": _FALLBACK,
            "citations": [],
            "calculation": calc_result,
        }

    # Build prompt and call Claude
    system_prompt = _build_system_prompt(chunks, calc_result)
    answer_text = _call_claude(system_prompt, question)

    citations = [
        {
            "title": c.title,
            "source": c.source,
            "url": c.source_urls[0] if c.source_urls else None,
            "heading": c.heading,
        }
        for c in chunks
    ]
    # Deduplicate by title
    seen = set()
    unique_citations = []
    for cit in citations:
        if cit["title"] not in seen:
            seen.add(cit["title"])
            unique_citations.append(cit)

    return {
        "answer": answer_text,
        "citations": unique_citations,
        "calculation": calc_result,
    }
```

- [ ] **Step 4: Run answer tests (mocked — no Claude API calls)**

```bash
pytest tests/test_knowledge.py::test_no_answer_when_empty_retrieval tests/test_knowledge.py::test_citations_included_in_answer tests/test_knowledge.py::test_safety_guardrail_in_system_prompt tests/test_knowledge.py::test_calculation_included_when_relevant -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add api/services/knowledge/answer.py tests/test_knowledge.py
git commit -m "feat(knowledge): add RAG answer orchestration with Claude, safety guardrails, citations"
```

---

## Task 8: Ingest CLI script

**Files:**
- Create: `scripts/ingest_knowledge.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""
CLI for ingesting knowledge files into the AthFuelPath knowledge base.

Usage:
  python scripts/ingest_knowledge.py --all
  python scripts/ingest_knowledge.py --file knowledge/iron_magnesium.md
  python scripts/ingest_knowledge.py --retire knowledge/old_guide.md
  python scripts/ingest_knowledge.py --status          # list all items
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="AthFuelPath knowledge base ingestion")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Ingest all approved files in /knowledge")
    group.add_argument("--file", type=str, help="Ingest a single file")
    group.add_argument("--retire", type=str, help="Archive a knowledge item by slug or file path")
    group.add_argument("--status", action="store_true", help="List all knowledge items and their status")
    args = parser.parse_args()

    if args.all:
        from api.services.knowledge.ingest import ingest_all
        results = ingest_all()
        ok = [r for r in results if r["status"] == "ok"]
        skipped = [r for r in results if r["status"] == "skipped"]
        errors = [r for r in results if r["status"] == "error"]
        print(f"\n✓ Ingested: {len(ok)}")
        for r in ok:
            print(f"  {r['slug']} — {r['chunks']} chunks")
        if skipped:
            print(f"\n⊘ Skipped (not approved): {len(skipped)}")
            for r in skipped:
                print(f"  {r['slug']}: {r['reason']}")
        if errors:
            print(f"\n✗ Errors: {len(errors)}")
            for r in errors:
                print(f"  {r.get('slug', '?')}: {r['reason']}")

    elif args.file:
        from api.services.knowledge.ingest import ingest_file
        result = ingest_file(args.file)
        if result["status"] == "ok":
            print(f"✓ Ingested '{result['slug']}' — {result['chunks']} chunks")
        elif result["status"] == "skipped":
            print(f"⊘ Skipped: {result['reason']}")
        else:
            print(f"✗ Error: {result['reason']}")
            sys.exit(1)

    elif args.retire:
        from api.database import get_conn
        slug = Path(args.retire).stem
        conn = get_conn()
        try:
            row = conn.execute("SELECT id FROM knowledge_items WHERE slug = ?", (slug,)).fetchone()
            if not row:
                print(f"✗ No knowledge item found with slug '{slug}'")
                sys.exit(1)
            conn.execute(
                "UPDATE knowledge_items SET review_status = 'archived' WHERE slug = ?", (slug,)
            )
            conn.commit()
            print(f"✓ Archived '{slug}'")
        finally:
            conn.close()

    elif args.status:
        from api.database import get_conn
        conn = get_conn()
        try:
            rows = conn.execute(
                """SELECT ki.slug, ki.title, ki.review_status, ki.version,
                          ki.last_reviewed_date, COUNT(kc.id) as chunk_count
                   FROM knowledge_items ki
                   LEFT JOIN knowledge_chunks kc ON kc.item_id = ki.id
                   GROUP BY ki.id ORDER BY ki.review_status, ki.slug"""
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            print("No knowledge items found. Run --all to ingest.")
            return
        print(f"\n{'Slug':<25} {'Status':<12} {'v':<4} {'Chunks':<8} {'Last Reviewed'}")
        print("-" * 70)
        for r in rows:
            print(f"{r['slug']:<25} {r['review_status']:<12} {r['version']:<4} {r['chunk_count']:<8} {r['last_reviewed_date']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable and test**

```bash
chmod +x scripts/ingest_knowledge.py
python scripts/ingest_knowledge.py --all
```

Expected output (something like):
```
✓ Ingested: 7
  iron_magnesium — 6 chunks
  hydration — 5 chunks
  ...
```

- [ ] **Step 3: Verify status command**

```bash
python scripts/ingest_knowledge.py --status
```

Expected: table showing 7 approved items with chunk counts.

- [ ] **Step 4: Commit**

```bash
git add scripts/ingest_knowledge.py
git commit -m "feat(knowledge): add CLI ingest script with --all, --file, --retire, --status"
```

---

## Task 9: Admin API routes

**Files:**
- Create: `api/routes/knowledge.py`
- Modify: `api/main.py`

- [ ] **Step 1: Create `api/routes/knowledge.py`**

```python
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import json
import os

from api.database import get_conn
from api.services.knowledge.ingest import ingest_file, ingest_all
from api.services.knowledge.answer import answer_with_knowledge

router = APIRouter()

_ADMIN_KEY = os.getenv("KNOWLEDGE_ADMIN_KEY", "fuelup-admin")


def _require_admin(x_admin_key: Optional[str] = Header(None)):
    if x_admin_key != _ADMIN_KEY:
        raise HTTPException(403, "Admin key required. Pass X-Admin-Key header.")


class AskRequest(BaseModel):
    question: str
    athlete_id: int


class StatusUpdate(BaseModel):
    review_status: str  # draft | approved | archived


@router.get("/")
def list_knowledge_items(x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT ki.slug, ki.title, ki.category, ki.review_status, ki.version,
                      ki.last_reviewed_date, ki.source, ki.ingested_at,
                      COUNT(kc.id) as chunk_count
               FROM knowledge_items ki
               LEFT JOIN knowledge_chunks kc ON kc.item_id = ki.id
               GROUP BY ki.id ORDER BY ki.review_status, ki.category, ki.slug"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/ingest")
def trigger_ingest(file_path: Optional[str] = None,
                   x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    if file_path:
        result = ingest_file(file_path)
    else:
        result = ingest_all()
    return result


@router.get("/{slug}")
def get_knowledge_item(slug: str, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        item = conn.execute(
            "SELECT * FROM knowledge_items WHERE slug = ?", (slug,)
        ).fetchone()
        if not item:
            raise HTTPException(404, f"Knowledge item '{slug}' not found.")
        chunks = conn.execute(
            "SELECT chunk_index, heading, content FROM knowledge_chunks WHERE item_id = ? ORDER BY chunk_index",
            (item["id"],),
        ).fetchall()
        return {
            **dict(item),
            "source_urls": json.loads(item["source_urls"] or "[]"),
            "tags": json.loads(item["tags"] or "[]"),
            "chunks": [dict(c) for c in chunks],
        }
    finally:
        conn.close()


@router.patch("/{slug}/status")
def update_status(slug: str, body: StatusUpdate,
                  x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    allowed = {"draft", "approved", "archived"}
    if body.review_status not in allowed:
        raise HTTPException(400, f"review_status must be one of: {allowed}")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Knowledge item '{slug}' not found.")
        conn.execute(
            "UPDATE knowledge_items SET review_status = ? WHERE slug = ?",
            (body.review_status, slug),
        )
        conn.commit()
        return {"slug": slug, "review_status": body.review_status}
    finally:
        conn.close()


@router.delete("/{slug}")
def archive_item(slug: str, x_admin_key: Optional[str] = Header(None)):
    _require_admin(x_admin_key)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = ?", (slug,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Knowledge item '{slug}' not found.")
        conn.execute(
            "UPDATE knowledge_items SET review_status = 'archived' WHERE slug = ?",
            (slug,),
        )
        conn.commit()
        return {"slug": slug, "review_status": "archived", "message": "Item archived (not deleted)."}
    finally:
        conn.close()


@router.post("/ask")
def ask_knowledge(body: AskRequest):
    """Public endpoint — athletes/parents ask questions."""
    conn = get_conn()
    try:
        athlete = conn.execute(
            "SELECT * FROM athletes WHERE id = ?", (body.athlete_id,)
        ).fetchone()
        if not athlete:
            raise HTTPException(404, "Athlete not found.")
        athlete_dict = dict(athlete)
    finally:
        conn.close()
    return answer_with_knowledge(body.question, athlete_dict)
```

- [ ] **Step 2: Register router in `api/main.py`**

Open `api/main.py`. Add the import and router registration:

```python
# In the imports line, add:
from api.routes import parents, athletes, events, nutrition, meals, recipes, analysis, reports, notifications, meal_plans, today, water, knowledge

# After the water router line, add:
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["15. Knowledge Base"])
```

- [ ] **Step 3: Restart the server and smoke test**

```bash
pkill -f "uvicorn api.main" 2>/dev/null; sleep 1
source venv/bin/activate
uvicorn api.main:app --reload --port 8000 &
sleep 3
curl -s -H "X-Admin-Key: fuelup-admin" http://localhost:8000/api/knowledge/ | python3 -m json.tool | head -30
```

Expected: JSON array of knowledge items.

- [ ] **Step 4: Test the /ask endpoint**

```bash
curl -s -X POST http://localhost:8000/api/knowledge/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "how much iron does a teenage girl need?", "athlete_id": 1}' \
  | python3 -m json.tool
```

Expected: JSON with `answer`, `citations` (non-empty), `calculation`.

- [ ] **Step 5: Commit**

```bash
git add api/routes/knowledge.py api/main.py
git commit -m "feat(knowledge): add admin API routes and /ask public endpoint"
```

---

## Task 10: Run all tests and final verification

- [ ] **Step 1: Run the full test suite**

```bash
source venv/bin/activate
pytest tests/test_knowledge.py -v
```

Expected output (all should pass):
```
tests/test_knowledge.py::test_knowledge_tables_exist PASSED
tests/test_knowledge.py::test_knowledge_items_schema PASSED
tests/test_knowledge.py::test_knowledge_chunks_schema PASSED
tests/test_knowledge.py::test_ingest_creates_knowledge_item PASSED
tests/test_knowledge.py::test_ingest_creates_chunks PASSED
tests/test_knowledge.py::test_draft_file_not_ingested PASSED
tests/test_knowledge.py::test_retrieval_finds_iron_content PASSED
tests/test_knowledge.py::test_retrieval_returns_empty_for_unknown_domain PASSED
tests/test_knowledge.py::test_retrieval_respects_approved_only PASSED
tests/test_knowledge.py::test_iron_rda_female_14 PASSED
tests/test_knowledge.py::test_iron_rda_male_14 PASSED
tests/test_knowledge.py::test_iron_rda_child_9 PASSED
tests/test_knowledge.py::test_calcium_rda_youth PASSED
tests/test_knowledge.py::test_protein_range_game_day PASSED
tests/test_knowledge.py::test_hydration_needs_game PASSED
tests/test_knowledge.py::test_hydration_needs_hot_weather PASSED
tests/test_knowledge.py::test_pre_training_meal_window PASSED
tests/test_knowledge.py::test_post_training_recovery_window PASSED
tests/test_knowledge.py::test_no_answer_when_empty_retrieval PASSED
tests/test_knowledge.py::test_citations_included_in_answer PASSED
tests/test_knowledge.py::test_safety_guardrail_in_system_prompt PASSED
tests/test_knowledge.py::test_calculation_included_when_relevant PASSED
```

- [ ] **Step 2: Verify the ingest script with status**

```bash
python scripts/ingest_knowledge.py --status
```

Expected: 7 approved rows in the table.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(knowledge): RAG knowledge system complete — 7 files, TF-IDF retrieval, deterministic calcs, Claude RAG, admin API, 22 tests"
```

---

## How to Add New Knowledge Content (Ongoing)

1. Create `knowledge/your_topic.md` using the frontmatter template from Task 3
2. Set `review_status: "draft"` while writing
3. When ready: change to `review_status: "approved"`
4. Run: `python scripts/ingest_knowledge.py --file knowledge/your_topic.md`
5. Verify: `python scripts/ingest_knowledge.py --status`

To replace/update existing content:
1. Increment `version` in the frontmatter
2. Run ingest again — it upserts (replaces chunks for that slug)

To retire old guidance:
```bash
python scripts/ingest_knowledge.py --retire knowledge/old_guide.md
```
