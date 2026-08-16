# Window Vocabulary Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the user-facing nutrition "window" vocabulary (Fuel Before / Recharge Snack / Rebuild Meal / Rebuild Breakfast titles, PRE-EVENT / POST-EVENT subtitle tags) across the backend label generator, push-notification copy, and the mobile app — without touching any persisted data, schema, calc logic, or API contracts.

**Architecture:** The live window engine (`window_engine_v2.py`, enabled in prod via `EVENT_RELATIVE_WINDOWS=true`) *generates* card titles and subtitle tags at runtime; the active web tabs and mobile cards render those strings, so they inherit renames automatically. Only three places hold hardcoded user-facing strings: the engine itself, `notification_service.py` push copy, and a handful of mobile screens. Plus one explicitly-requested internal rename: the mobile Fuel Finder `food-catalog.ts` kebab keys.

**Tech Stack:** Python 3.11 / FastAPI / pytest (backend, repo `/Users/mayurkhera/AthFuelPath`); React Native / Expo SDK 54 / TypeScript / jest (mobile, repo `/Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile`, **not a git repo**).

---

## Canonical rename map (authoritative)

**Titles:** Pre-Game Meal / Pre-Training Meal → **Fuel Before** · Recovery Snack → **Recharge Snack** · Recovery Meal → **Rebuild Meal** · Recovery Breakfast → **Rebuild Breakfast** · Top-Up Snack → *(unchanged)*

**Subtitle tags (text only; color/`category_key` unchanged):** Fuel Before / High Carbs / Fuel Window → **PRE-EVENT** · Fuel After / High Protein + Carbs / Recovery Focus → **POST-EVENT**

**Fuel Finder tabs (window-title style):** Pre-Game → **Fuel Before** · Top-Up *(unchanged)* · During *(unchanged)* · Recovery → **Recharge** · Recovery Meal → **Rebuild**

**Mobile food-catalog internal kebab ids:** `pre-game-meal` → `fuel-before` · `recovery-snack` → `recharge-snack` · `recovery-meal` → `rebuild-meal` · `top-up` / `during` *(unchanged)*

## Explicitly OUT of scope (do NOT touch — verified)
- `competition_level` → `sport_type`, `fueling_targets.py` v2.0, intensity rework (separate specs).
- **Persisted / contract keys, byte-for-byte unchanged:** `window_key` values (`pre_event_meal`, `fuel_after_primary`, `fuel_after_second`, `proper_breakfast_after`, `top_up_snack`, `quick_morning_snack`, `everyday_*`, `refuel_ready_*`, `between_games_*`), `window_type` (`pre_fuel`/`recovery`/`hydration`), `category` (`fuel_before`/`fuel_after`/`everyday`/`quick_snack`/`fuel_during`), `category_key` (`carb`/`recovery`/`balanced`/`hydrate`), recipe `category` keys, and the AsyncStorage pref `key`s in mobile `settings/notifications.tsx` (`training_pre_event`, `game_pre_game_meal`, …).
- **Legacy `window_templates.py` clock engine** — dead in prod (`EVENT_RELATIVE_WINDOWS=true`); uses off-table vocab ("Recovery Window", "Proper Breakfast"). Leave entirely.
- **Legacy web screens** `HomeScreen.jsx` (meal-log tab), `RecipesScreen.jsx` (recipes tab), web `NotificationsScreen.jsx` — not in the `AppShell` `TABS` nav, unreachable. Off-table vocab. Leave.
- **Mobile coach intent buckets** (`constants/coachPrompts.ts` `PromptBucket`, `app/coach/index.tsx` resolver `key.includes("recovery_meal")`) — internal-only, never user-visible, separate underscore vocabulary with its own consumer. Leave (avoids churn/risk).
- Descriptive prose copy (e.g. `MealPlannerScreen.jsx` `DAY_HERO` sentences) — not labels/tags.

---

## Task 1: Backend — window engine card labels

**Files:**
- Modify: `api/services/window_engine_v2.py` (lines ~242, 245, 270, 321, 324, 346, 349, 374, 377 — confirm by string match, not line number)

- [ ] **Step 1: Confirm current strings**

Run: `grep -nE 'label\s*=|category_label\s*=' api/services/window_engine_v2.py | sed -n '1,40p'`
Expected: see `label = "Pre-Game Meal" if is_game else "Pre-Training Meal"` and the `category_label = "Fuel Before"/"Fuel After"` lines listed in Step 2.

- [ ] **Step 2: Apply the title + subtitle edits**

Make exactly these replacements in `api/services/window_engine_v2.py` (match on the full line; leave every `category=`, `category_key=`, `window_key=`, `macro_focus=` untouched):

| Current line | New |
|---|---|
| `label          = "Pre-Game Meal" if is_game else "Pre-Training Meal",` (pre_event_meal) | `label          = "Fuel Before",` |
| `category_label = "Fuel Before",` (pre_event_meal block, ~245) | `category_label = "PRE-EVENT",` |
| `category_label = "Fuel Before",` (top_up_snack block, ~270) | `category_label = "PRE-EVENT",` |
| `label          = "Recovery Snack",` (fuel_after_primary, ~321) | `label          = "Recharge Snack",` |
| `category_label = "Fuel After",` (fuel_after_primary, ~324) | `category_label = "POST-EVENT",` |
| `label          = "Recovery Breakfast",` (proper_breakfast_after, ~346) | `label          = "Rebuild Breakfast",` |
| `category_label = "Fuel After",` (proper_breakfast_after, ~349) | `category_label = "POST-EVENT",` |
| `label          = "Recovery Meal",` (fuel_after_second, ~374) | `label          = "Rebuild Meal",` |
| `category_label = "Fuel After",` (fuel_after_second, ~377) | `category_label = "POST-EVENT",` |

There are three identical `category_label = "Fuel After",` lines (324, 349, 377) and two identical `category_label = "Fuel Before",` lines (245, 270) — all five become the PRE/POST-EVENT value shown; replace-all is safe here because every `"Fuel After"` → `POST-EVENT` and every `"Fuel Before"` (as a `category_label` value) → `PRE-EVENT` in this file. Do NOT touch `category = "fuel_before"` / `category = "fuel_after"` (lowercase keys).

Leave unchanged: `"Top-Up Snack"` (267), `"Quick Morning Snack"` + `"Light Carbs"` (217/220), `"Halftime Fuel"`/`"Hydration Break"` + `"Fuel During"` (295/298), and all merged-window labels.

- [ ] **Step 3: Verify no contract keys moved**

Run: `git diff api/services/window_engine_v2.py | grep -E '^[-+]' | grep -iE 'window_key|category\s*=|category_key|window_type'`
Expected: **no output** (only label/category_label lines changed).

- [ ] **Step 4: Run the engine's tests**

Run: `source venv/bin/activate && python -m pytest tests/test_window_templates.py tests/test_today_service.py tests/test_fuel_report_service.py -q`
Expected: PASS. If any test asserts an old title string (e.g. `== "Recovery Snack"`), update that assertion to the new title and re-run.

- [ ] **Step 5: Commit**

```bash
git add api/services/window_engine_v2.py tests/
git commit -m "feat(windows): rename card titles + subtitle tags to new vocab"
```

---

## Task 2: Backend — push-notification copy

**Files:**
- Modify: `api/services/notification_service.py` (lines 179, 180, 186, 208, 212, 224)
- Test: `tests/test_notification_service.py`

- [ ] **Step 1: Apply the push-title edits**

In `api/services/notification_service.py`, replace these title strings (keep the message bodies and all `window_key.startswith(...)` guards exactly as-is):

| Current | New |
|---|---|
| `return "Pre-Game Meal", f"Your fuel window is open. Eat now — {en} starts at {st}."` (179) | `return "Fuel Before", f"Your fuel window is open. Eat now — {en} starts at {st}."` |
| `return "Pre-Training Meal", "Fuel up before your session — energy for a strong one."` (180) | `return "Fuel Before", "Fuel up before your session — energy for a strong one."` |
| `return "Recovery Window", "Eat in the next 30 min. Your muscles are ready to recover."` (186) | `return "Recharge Snack", "Eat in the next 30 min. Your muscles are ready to recover."` |
| `f"{first_name}'s Pre-Game Meal",` (208) | `f"{first_name}'s Fuel Before",` |
| `f"{first_name}'s Pre-Training Meal",` (212) | `f"{first_name}'s Fuel Before",` |
| `f"{first_name}'s Recovery Window",` (224) | `f"{first_name}'s Recharge Snack",` |

Leave unchanged: `"Early Start"`, `"Recover & Refuel"`, `"Quick Refuel"`, `"Between Games"`, `"Fuel Window Open"`, `"Early Game for {first_name}"`, `"Refuel for {first_name}"` (not in rename table).

- [ ] **Step 2: Run notification tests**

Run: `source venv/bin/activate && python -m pytest tests/test_notification_service.py -q`
Expected: PASS. The existing tests pass `"Pre-Game Meal"` as an arbitrary title *argument* to `send_notification` (lines ~260–333) — those are inputs, not copy assertions, and remain valid. If any test asserts `_athlete_copy`/`_parent_copy` output equals an old title, update it to the new title above and re-run.

- [ ] **Step 3: Commit**

```bash
git add api/services/notification_service.py tests/test_notification_service.py
git commit -m "feat(notifications): rename push-notification window titles to new vocab"
```

---

## Task 3: Backend — full regression gate

**Files:** none (verification only)

- [ ] **Step 1: Run the whole backend suite**

Run: `source venv/bin/activate && python -m pytest -q`
Expected: PASS (same pass/fail baseline as `main` minus any old-title assertions already fixed). Investigate and fix any failure referencing a renamed string before proceeding.

- [ ] **Step 2: Leftover-vocab sweep (display positions only)**

Run: `grep -rnE '"(Pre-Game Meal|Pre-Training Meal|Recovery Snack|Recovery Meal|Recovery Breakfast)"' --include='*.py' --exclude-dir=venv api/ | grep -v window_templates.py`
Expected: **no output** (window_templates.py legacy engine is intentionally excluded/untouched).

- [ ] **Step 3: Contract-integrity check vs main**

Run: `git diff main -- api/ | grep -E '^[-+]' | grep -iE "window_key\s*=|window_type\s*=|category\s*=\s*[\"']|category_key\s*=|competition_level|CHO_FACTOR"`
Expected: **no output** — confirms no persisted/contract key or factor constant changed.

---

## Task 4: Mobile — Fuel Finder tab labels

**Repo:** `/Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile`

**Files:**
- Modify: `app/(app)/fuel-finder/index.tsx` (CATEGORIES array, lines 38, 41, 42 — labels only)

- [ ] **Step 1: Snapshot the non-git mobile repo (safety net)**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && cp -r . ../fuelup-mobile.backup-2026-06-24` (skip if a snapshot/branch already exists)
Expected: a sibling backup directory created. (This repo has no git; this is the rollback path.)

- [ ] **Step 2: Rename the tab `label` strings (NOT the `id`s in this task)**

In `app/(app)/fuel-finder/index.tsx` CATEGORIES:

| Line | Current | New |
|---|---|---|
| 38 | `{ id: "pre-game-meal",  label: "Pre-Game",  ...` | `label: "Fuel Before"` |
| 41 | `{ id: "recovery-snack", label: "Recovery",  ...` | `label: "Recharge"` |
| 42 | `{ id: "recovery-meal",  label: "Recovery Meal", ...` | `label: "Rebuild"` |

Leave `top-up` ("Top-Up"), `during` ("During"), `hydration`, `label-check` labels unchanged. Leave all `id` values unchanged in this task (kebab-id rename is Task 6).

- [ ] **Step 3: Typecheck**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no new errors.

- [ ] **Step 4: Commit-equivalent checkpoint**

Run: `grep -nE 'label: "(Fuel Before|Recharge|Rebuild)"' "app/(app)/fuel-finder/index.tsx"`
Expected: three matching lines. (No git here; this grep is the done-check.)

---

## Task 5: Mobile — notification settings row labels

**Files:**
- Modify: `app/(app)/settings/notifications.tsx` (TRAINING_ROWS line 43–44, GAME_ROWS line 49)

- [ ] **Step 1: Rename the display `label`s (keep every `key` value unchanged)**

In `app/(app)/settings/notifications.tsx`:

| Line | Current `label` | New `label` |
|---|---|---|
| 43 | `"Pre-Training Reminder"` (key `training_pre_event`) | `"Fuel Before"` |
| 44 | `"Recovery Window"` (key `training_recovery`) | `"Recharge Snack"` |
| 49 | `"Pre-Game Meal"` (key `game_pre_game_meal`) | `"Fuel Before"` |

Leave unchanged: `"Breakfast Reminder"` (45), `"Top-Up Snack"` (50), `"Hydration Check"` (51), `"Between Games"` (52). **Do NOT change any `key:` value** — those are AsyncStorage pref keys (data contract).

- [ ] **Step 2: Verify keys untouched**

Run: `grep -nE 'key: "(training_pre_event|training_recovery|game_pre_game_meal)"' "app/(app)/settings/notifications.tsx"`
Expected: three lines, all original key names intact.

- [ ] **Step 3: Typecheck**

Run: `npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no new errors.

---

## Task 6: Mobile — food-catalog internal kebab-id rename

**Files:**
- Modify: `data/food-catalog.ts` (WindowId type, WINDOW_GROUP_ORDER keys, SLOT_TAB_MAP values, ~100 `FoodWindow.id` entries)
- Modify: `app/(app)/fuel-finder/index.tsx` (CATEGORIES `id`s line 38/41/42, `TabId` type, default `useState<TabId>(... ?? "pre-game-meal")` line 152)

Rename three kebab tokens app-wide in mobile: `pre-game-meal`→`fuel-before`, `recovery-snack`→`recharge-snack`, `recovery-meal`→`rebuild-meal`. (`top-up`, `during` stay.) These are internal ids only; backend `slot_name`s like `pre_event_meal` stay unchanged and continue to map via `SLOT_TAB_MAP`.

- [ ] **Step 1: Confirm the only two files containing these kebab tokens**

Run: `grep -rlE 'pre-game-meal|recovery-snack|recovery-meal' --include='*.ts' --include='*.tsx' --exclude-dir=node_modules .`
Expected: exactly `./data/food-catalog.ts` and `./app/(app)/fuel-finder/index.tsx`. If any other file appears (e.g. a deep-link caller), add it to the edit set in Step 2.

- [ ] **Step 2: Apply the three replacements in those files**

In `data/food-catalog.ts` and `app/(app)/fuel-finder/index.tsx`, replace-all (whole-token, hyphenated):
- `"pre-game-meal"` → `"fuel-before"`
- `"recovery-snack"` → `"recharge-snack"`
- `"recovery-meal"` → `"rebuild-meal"`

This covers: `WindowId`/`TabId` unions, `WINDOW_GROUP_ORDER` keys, `SLOT_TAB_MAP` values (lines 77/79–82/83), every `FoodWindow.id`, the CATEGORIES `id`s, and the `useState<TabId>(... ?? "pre-game-meal")` default (line 152 → `"fuel-before"`). Do NOT touch the underscore `slot_name` keys of `SLOT_TAB_MAP` (`pre_event_meal`, `fuel_after_primary`, `fuel_after_second`, `proper_breakfast_after`, `refuel_ready`, `between_games`) — those are the backend contract side.

- [ ] **Step 3: Verify old kebab ids fully gone**

Run: `grep -rnE 'pre-game-meal|recovery-snack|recovery-meal' --include='*.ts' --include='*.tsx' --exclude-dir=node_modules .`
Expected: **no output**.

- [ ] **Step 4: Typecheck**

Run: `npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no new errors (the renamed unions must resolve everywhere they're used).

---

## Task 7: Mobile — update test mocks + full mobile regression

**Files:**
- Modify: `__tests__/store/coachThreadStore.test.ts` (lines 209/212/244/247)

- [ ] **Step 1: Update mock window/category labels to new reality**

In `__tests__/store/coachThreadStore.test.ts`, update the mock values so they reflect what the backend now emits:
- `windowLabel: "Pre-Game Meal"` (209, 244) → `windowLabel: "Fuel Before"`
- `categoryLabel: "Fuel Before"` (212, 247) → `categoryLabel: "PRE-EVENT"`

Leave `windowLabel: "Breakfast"` / `categoryLabel: "Everyday"` (230/233) and `__tests__/components/fuelGaugePresenter.test.ts` `category_key: "carb"/"recovery"` (181–182) unchanged (`category_key` is a contract value, not renamed).

- [ ] **Step 2: Run the mobile test suite**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npm test -- --watchAll=false 2>&1 | tail -30`
Expected: PASS. Fix any assertion still referencing an old label.

- [ ] **Step 3: Typecheck (whole app)**

Run: `npx tsc --noEmit 2>&1 | grep -v node_modules`
Expected: no errors.

- [ ] **Step 4: Manual Expo smoke (render check)**

Run: `./node_modules/.bin/expo start -c --go` and load: Today (card title shows "Fuel Before"/"Recharge Snack"; subtitle tag shows PRE-EVENT/POST-EVENT via `WindowCard.tsx` `category_label.toUpperCase()`), Fuel Finder (tabs read Fuel Before / Top-Up / During / Recharge / Rebuild; tapping each loads foods — confirms kebab-id rename intact), Meal Plan, Settings → Notifications (rows read Fuel Before / Recharge Snack / Breakfast Reminder).
Expected: correct labels; no blank Fuel Finder tabs (blank = a kebab id mismatch from Task 6).

---

## Task 8: Web — confirm inheritance + final cross-repo sweep

**Files:** none (verification only)

- [ ] **Step 1: Confirm active web tabs render backend labels (no hardcoded titles)**

Run: `cd /Users/mayurkhera/AthFuelPath/frontend && grep -rnE 'Recovery (Snack|Meal|Breakfast)|Pre-Game Meal|Pre-Training Meal' src/pages/Today.jsx src/MealPlannerScreen.jsx src/NutritionDashboard.jsx`
Expected: **no output** — active tabs pull `label`/`category_label` from the API, so they inherit the rename. (Legacy `HomeScreen.jsx`/`RecipesScreen.jsx` are intentionally out of scope and not in the `TABS` nav.)

- [ ] **Step 2: Web build + lint**

Run: `cd /Users/mayurkhera/AthFuelPath/frontend && npm run build && npm run lint`
Expected: build succeeds, lint clean (no changes were made to web; this confirms nothing broke).

- [ ] **Step 3: End-to-end label check against a running backend (optional but recommended)**

Run backend (`uvicorn api.main:app --reload --port 8000` with `EVENT_RELATIVE_WINDOWS=true`), hit `GET /api/athletes/<id>/today` for an athlete with a game event, and confirm the JSON `windows[].label` / `windows[].category_label` read "Fuel Before"/"PRE-EVENT", "Recharge Snack"/"POST-EVENT", "Rebuild Meal"/"POST-EVENT".
Expected: new vocabulary in the live API response.

- [ ] **Step 4: Final commit (backend repo) + branch wrap**

```bash
cd /Users/mayurkhera/AthFuelPath
git add -A && git commit -m "chore(windows): finalize vocabulary rename regression checks" --allow-empty
```
Then follow the finishing-a-development-branch flow (open PR for `feat/window-vocab-rename`). For the mobile repo (no git), package the diff against `../fuelup-mobile.backup-2026-06-24` for review.

---

## Self-review notes
- **Spec coverage:** titles (Task 1), PRE/POST-EVENT subtitle tags (Task 1), push copy (Task 2), Fuel Finder tabs (Task 4), mobile notification labels (Task 5), food-catalog kebab rename (Task 6), test updates (Tasks 1/2/7), web inheritance + regression (Tasks 3/8). All spec §4 rows mapped.
- **Contract safety:** explicit "leave unchanged" guards for `window_key`/`window_type`/`category`/`category_key`, recipe categories, AsyncStorage pref keys, and `competition_level`; Tasks 3 & 8 grep-assert no contract drift.
- **No placeholders:** every edit step lists exact current→new strings.
- **Consistency:** "Recharge Snack" is used for `fuel_after_primary` everywhere (engine label Task 1, push title Task 2 line 186, notification settings row Task 5 line 44); Fuel Finder uses the short "Recharge"/"Rebuild" tab forms per the approved window-title style.
