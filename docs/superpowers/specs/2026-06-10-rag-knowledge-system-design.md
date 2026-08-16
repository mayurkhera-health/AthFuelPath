# RAG Knowledge System — Design Spec
**Date:** 2026-06-10  
**App:** AthFuelPath Soccer Nutrition Platform  
**Stack:** Python / FastAPI / SQLite / Anthropic Claude (claude-sonnet-4-6)

---

## 1. Goal

Build a retrieval-augmented generation (RAG) system that lets Claude answer youth-athlete nutrition questions **only from approved, cited knowledge** — no invented formulas, no hallucinated facts. Deterministic calculations stay in Python code; Claude only explains results in human language.

---

## 2. Architecture

```
User question (athlete/parent)
        │
        ▼
┌─────────────────────┐
│  Retrieval Layer    │  TF-IDF search over SQLite knowledge_chunks
│  (retrieval.py)     │  Returns top-N chunks + metadata
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Calculation Layer  │  If question matches a calculation type,
│  (calculations.py)  │  run deterministic Python function first
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Answer Layer       │  Claude receives: retrieved chunks +
│  (answer.py)        │  optional calculation result + question
│                     │  Answers ONLY from provided context
└─────────────────────┘
        │
        ▼
   Response + citations
```

**No OpenAI. No vector DB. No new accounts.**  
Uses: `sklearn` TF-IDF, existing SQLite DB, existing Anthropic SDK.

---

## 3. Knowledge File Format

Files live in `/knowledge/` as Markdown with YAML frontmatter.

```markdown
---
title: "Iron Requirements for Female Youth Athletes"
category: "micronutrients"
source: "NIH Office of Dietary Supplements / ACSM / AND"
source_urls:
  - "https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/"
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["iron", "minerals", "female-athletes", "fatigue", "performance"]
review_status: "approved"   # draft | approved | archived
version: 1
---

## Content here...
```

**Categories:** `macronutrients`, `micronutrients`, `hydration`, `meal-timing`, `recovery`, `game-day`, `safety`

**review_status lifecycle:**
- `draft` — created, not yet usable for answers
- `approved` — active, used in retrieval
- `archived` — replaced by newer version, not used

---

## 4. Database Schema (SQLite)

Two new tables added to `fuelup.db`:

```sql
CREATE TABLE knowledge_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,           -- filename without extension
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT,
    source_urls TEXT,                    -- JSON array
    last_reviewed_date TEXT,
    applicable_age_range TEXT,
    tags TEXT,                           -- JSON array
    review_status TEXT DEFAULT 'draft',
    version INTEGER DEFAULT 1,
    file_path TEXT NOT NULL,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER REFERENCES knowledge_items(id),
    chunk_index INTEGER NOT NULL,
    heading TEXT,                        -- nearest H2/H3 above this chunk
    content TEXT NOT NULL,
    tfidf_tokens TEXT,                   -- preprocessed tokens for search
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. File Structure

```
/knowledge/
  iron_magnesium.md
  hydration.md
  pre_practice_meals.md
  post_practice_recovery.md
  game_day_nutrition.md
  weekly_checkin.md
  safety_red_flags.md

api/services/knowledge/
  __init__.py
  ingest.py          ← parse MD, chunk, store in SQLite
  retrieval.py       ← TF-IDF search, return top-N chunks + metadata
  calculations.py    ← deterministic Python functions only
  answer.py          ← orchestrate retrieval + calc + Claude prompt

scripts/
  ingest_knowledge.py   ← CLI: python scripts/ingest_knowledge.py [--all | --file path]

api/routes/
  knowledge.py          ← admin CRUD endpoints

tests/
  test_knowledge.py
```

---

## 6. Ingestion Pipeline (`ingest.py`)

1. Parse YAML frontmatter from Markdown file
2. Reject if `review_status != "approved"` (drafts are never ingested)
3. Split content into chunks at H2/H3 headings — max 400 tokens per chunk
4. Preprocess each chunk (lowercase, remove stopwords) → store as `tfidf_tokens`
5. Upsert into `knowledge_items` + `knowledge_chunks`
6. Rebuild TF-IDF index pickle after each ingest

**CLI usage:**
```bash
python scripts/ingest_knowledge.py --all          # ingest all approved files
python scripts/ingest_knowledge.py --file knowledge/iron_magnesium.md
python scripts/ingest_knowledge.py --retire knowledge/old_guide.md
```

---

## 7. Retrieval Layer (`retrieval.py`)

- Load TF-IDF index (pickle, rebuilt on ingest)
- Score all `approved` chunks against the query
- Return top 5 chunks with: `content`, `title`, `source`, `source_urls`, `heading`, `tags`
- Minimum similarity threshold: **0.05** — below this, return empty (triggers "not enough info" response)

```python
def retrieve(query: str, top_n: int = 5) -> list[KnowledgeChunk]:
    ...
```

---

## 8. Calculation Layer (`calculations.py`)

Deterministic Python functions. Claude never invents numbers — it only explains what these return.

| Function | Inputs | Output |
|---|---|---|
| `hydration_needs(weight_lbs, event_type, weather_hot)` | athlete weight, event type, heat flag | oz/day range |
| `protein_range(weight_lbs, event_type)` | weight, event type | g/day min–max |
| `pre_training_meal_window(start_time)` | event start time string | eat-by datetime |
| `post_training_recovery_window(end_time)` | event end time string | window open/close |
| `iron_rda(age, gender)` | age int, gender string | mg/day |
| `calcium_rda(age)` | age int | mg/day |
| `calorie_estimate(weight_lbs, age, gender, event_type)` | athlete stats | kcal/day range |

All functions return a `dict` with `value`, `unit`, `source`, and `explanation_hint`.

---

## 9. Answer Orchestration (`answer.py`)

```python
def answer_with_knowledge(question: str, athlete: dict) -> dict:
    # 1. Detect if question needs a calculation
    calc_result = maybe_calculate(question, athlete)

    # 2. Retrieve relevant knowledge chunks
    chunks = retrieve(question, top_n=5)

    # 3. If no chunks found → safe fallback
    if not chunks:
        return {
            "answer": "I don't have enough approved information to answer that confidently.",
            "citations": [],
            "calculation": None
        }

    # 4. Build Claude prompt — context-only, no invention
    prompt = build_rag_prompt(question, chunks, calc_result, athlete)

    # 5. Call Claude
    response = call_claude(prompt)

    # 6. Return answer + citations
    return {
        "answer": response,
        "citations": [{"title": c.title, "source": c.source, "url": c.source_urls[0]} for c in chunks],
        "calculation": calc_result
    }
```

**Claude system prompt rules (hardcoded):**
- Answer ONLY from the provided knowledge excerpts
- Never invent nutritional values, formulas, or dosages
- Always include the source label in your answer
- For any medical red flag (injury, fainting, eating disorder, severe dehydration): advise contacting a qualified professional
- Tone: supportive, simple, practical — written for a youth athlete aged 9–17

---

## 10. Admin API (`api/routes/knowledge.py`)

| Method | Path | Action |
|---|---|---|
| `GET` | `/api/knowledge/` | List all knowledge items (title, status, version, last_reviewed) |
| `POST` | `/api/knowledge/ingest` | Trigger ingest for one or all files |
| `PATCH` | `/api/knowledge/{slug}/status` | Change review_status (draft→approved→archived) |
| `GET` | `/api/knowledge/{slug}` | View full item + chunks |
| `DELETE` | `/api/knowledge/{slug}` | Archive (never hard delete) |

Admin-only: these routes check for an `admin` flag or a simple API key header for now.

---

## 11. Response Rules (enforced in Claude system prompt)

1. Age-appropriate language for 9–17 year olds
2. No medical diagnosis or treatment advice
3. Red flag triggers (always defer to professional): injury, fainting, eating disorder, severe dehydration, chest pain
4. Every answer that uses knowledge base content includes a citation
5. "What to do today" framing whenever possible
6. Numeric values only from `calculations.py` — never from Claude

---

## 12. Tests (`tests/test_knowledge.py`)

| Test | Checks |
|---|---|
| `test_retrieval_finds_iron_content` | Query "how much iron does a teenage girl need?" returns iron chunk |
| `test_retrieval_returns_empty_for_unknown` | Query "what is the stock price of Nike?" returns empty |
| `test_no_answer_when_empty_retrieval` | `answer_with_knowledge` returns fallback string when no chunks |
| `test_hydration_calculation_correct` | `hydration_needs(120, "game", False)` returns expected oz range |
| `test_protein_range_correct` | `protein_range(120, "strength")` returns values matching ACSM formula |
| `test_iron_rda_female_14` | `iron_rda(14, "female")` returns 15mg (NIH RDA) |
| `test_citations_included` | Every answer from knowledge base includes at least one citation |
| `test_safety_guardrail_eating_disorder` | Query about extreme restriction returns professional referral |
| `test_draft_not_retrieved` | Chunks from `draft` items never appear in results |
| `test_archived_not_retrieved` | Chunks from `archived` items never appear in results |

---

## 13. Sample Knowledge Files (to create)

| File | Content |
|---|---|
| `iron_magnesium.md` | RDA values, sports context from ACSM/AND/DC, food sources, athlete risks |
| `hydration.md` | Daily oz targets by event type, sweat rate, electrolyte guidance |
| `pre_practice_meals.md` | Timing windows, macros, example meals |
| `post_practice_recovery.md` | 30-min window, 3:1 carb:protein, casein at bedtime |
| `game_day_nutrition.md` | Night-before, breakfast, pre-game snack, halftime, recovery |
| `weekly_checkin.md` | How to assess fuel quality across the week |
| `safety_red_flags.md` | When to refer to a professional — medical red flags |

---

## 14. How to Add New Content (ongoing)

1. Create a `.md` file in `/knowledge/` using the frontmatter template above
2. Set `review_status: "draft"` until reviewed
3. When ready: change to `review_status: "approved"`
4. Run: `python scripts/ingest_knowledge.py --file knowledge/your_file.md`
5. The system picks it up immediately — no restart needed

To update existing content: increment `version`, set old file to `archived`, create new file.

---

## 15. Dependencies to Add

```
# requirements.txt additions
scikit-learn>=1.3.0    # TF-IDF
PyYAML>=6.0            # frontmatter parsing
pytest>=7.0            # tests (may already exist)
```

No new accounts. No new API keys. Everything uses existing Anthropic key.
