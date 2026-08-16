# Window Vocabulary Rename — Design Spec

**Date:** 2026-06-24
**Status:** Approved (design); pending implementation plan
**Branch:** `feat/window-vocab-rename`

## 1. Purpose

Rename the user-facing nutrition "window" vocabulary across the app so the
labels athletes and parents see match the new product language. This is a
**display / labelling change only**. It does **not** alter any persisted data,
database schema, calculation logic, or API contracts.

## 2. Background — why this is NOT a literal find/replace

The original find/replace table was written against conceptual names that do
not all exist in the codebase. The audit (2026-06-24) established:

- The codebase uses a runtime **window engine** (`api/services/window_engine_v2.py`)
  that *generates* card labels. Window titles are not stored.
- `BASE_FACTOR` does not exist; `CARB_FACTOR` is already `CHO_FACTOR`. Those two
  spec rows are stale — **no action**.
- `competition_level` is a real, DB-persisted column, but renaming it to
  `sport_type` is a semantic repurpose (tier → sport) tied to the separate
  v2.0 `fueling_targets.py` work. **Out of scope here.**
- The string `"Fuel Before"` plays **two roles**: today it is the *subtitle*
  (`category_label`); under the new scheme it becomes the *title* of the
  pre-event card while the subtitle becomes `PRE-EVENT`. A global string
  replace would corrupt both. Edits must be made **by role at each site**.

## 3. Scope

### In scope
- User-facing window/card **titles**.
- **Subtitle tag** text (the colored tag under each title).
- **Display-only internal keys** that never round-trip to the backend or DB
  (mobile `food-catalog.ts` kebab ids, mobile `coachPrompts.ts` intent vocab,
  mobile fuel-finder tab ids).
- Tests that assert the renamed display strings.

### Out of scope (separate specs — do not touch)
- `competition_level` → `sport_type` (column rename / repurpose / onboarding).
- `fueling_targets.py` v2.0 calc-engine migration.
- Intensity redefinition / duration-based `derive_intensity`.
- **All persisted / contract keys**, which stay byte-for-byte identical:
  - `window_key` values (`pre_event_meal`, `top_up_snack`, `fuel_after_primary`,
    `fuel_after_second`, `proper_breakfast_after`, `quick_morning_snack`,
    `everyday_*`, `refuel_ready_*`, `between_games_*`).
  - `window_type` values (`pre_fuel`, `recovery`, `hydration`).
  - `category` values (`fuel_before`, `fuel_after`, `everyday`, `quick_snack`,
    `fuel_during`) and `category_key` values (`carb`, `recovery`, `balanced`,
    `hydrate`).
  - Backend recipe `category` keys (`pre-game`, `pre-game-snack`,
    `post-game-recovery`) served by `/api/recipes/categories`.
- **No DB migration.** No `ALTER TABLE`. No data rewrite.

## 4. Canonical rename map

### Titles
| Old | New |
|---|---|
| Pre-Game Meal / Pre-Training Meal | **Fuel Before** |
| Recovery Snack | **Recharge Snack** |
| Recovery Meal | **Rebuild Meal** |
| Recovery Breakfast | **Rebuild Breakfast** |
| Top-Up Snack | *(unchanged)* |

### Subtitle tags (text only; tag color / `category_key` unchanged)
| Old subtitle variants | New |
|---|---|
| Fuel Before / High Carbs / Fuel Window | **PRE-EVENT** |
| Fuel After / High Protein + Carbs / Recovery Focus | **POST-EVENT** |

Notes:
- Merged / nudge labels not in the table ("Quick Morning Snack", "Halftime
  Fuel", "Fuel During", "Refuel", "Between Sessions") are **left unchanged**.
- Subtitle tag *color* is driven by `category_key`, which does not change; only
  the displayed tag text changes.

## 5. Governing principle (safety rule)

For every occurrence, classify the site as:

- **(a) Display string** — text rendered to the user → **rename** per §4.
- **(b) Data-contract key** — a value compared against backend data, persisted
  to the DB, used in a URL/param, or sent in an API payload → **leave
  unchanged**.

When a single string serves both roles (e.g. `"Fuel Before"` as subtitle vs.
the new title), resolve **per site by role**, never by global replace.

## 6. Per-surface change inventory

### 6.1 Backend (`api/services/window_engine_v2.py` only)
Engine-generated label strings, never persisted. Approx. lines (verify at edit
time): `242` (pre-event title), `245` (pre-event subtitle), `267/270` (top-up
subtitle), `321/324` (recharge snack title + subtitle), `346/349` (rebuild
breakfast title + subtitle), `374/377` (rebuild meal title + subtitle). The
`category=` keys on these same windows are **left unchanged**.
`window_templates.py` (legacy fallback engine) reviewed for the same labels.

### 6.2 Web (`frontend/src`)
- `HomeScreen.jsx` — hardcoded slot labels **and** the meal-photo lookup object
  keyed on those labels; key + every lookup must move together. FuelingGuide
  descriptive copy referencing "recovery snack/meal".
- `RecipesScreen.jsx` — `CATEGORY_LABELS` **values** (display) rename;
  **keys stay** (matched against backend `recipe.category`).
- `MealPlannerScreen.jsx` — `TAG_COLORS` "High Protein" tag + day-hero copy.
- `NotificationsScreen.jsx` — reminder titles + help copy.
- `pages/Today.jsx` — only if it renders any renamed label (verify; event-label
  map entries like "Recovery Day" are a different concept — leave).
- Live screens confirmed via `AppShell.jsx`: `Today` (home), `HomeScreen`
  (meal-log), `RecipesScreen` (recipes), `MealPlannerScreen` (meal-plan) all
  render.

### 6.3 Mobile (`AthFuelPath_Mobile/fuelup-mobile`) — largest surface, NOT a git repo
- `app/(app)/fuel-finder/index.tsx` — tab labels + internal kebab ids
  (`pre-game-meal`→`fuel-before`, `recovery-snack`→`recharge-snack`,
  `recovery-meal`→`rebuild-meal`, `top-up` unchanged) + `tabForSlot`.
- `data/food-catalog.ts` — ~100 entries keyed on the kebab ids above, plus the
  backend-slot→kebab-id map; rename the kebab ids **consistently together** so
  the slot map still resolves. Backend slot names (`pre_event_meal`, …) are the
  contract side and stay unchanged.
- `constants/coachPrompts.ts` — intent vocab type union + resolver
  (`recovery_snack`→`recharge_snack`, `recovery_meal`→`rebuild_meal`,
  `pre_training_meal`→`fuel_before`; `top_up_snack` unchanged). Internal to the
  coach prompt builder.
- `app/(app)/settings/notifications.tsx` — reminder row labels (keys unchanged).
- `components/meal-plan/WindowCard.tsx` — renders `category_label.toUpperCase()`;
  inherits PRE-EVENT/POST-EVENT automatically once the backend label changes.
- `__tests__/store/coachThreadStore.test.ts` and
  `__tests__/components/fuelGaugePresenter.test.ts` — update asserted labels.

## 7. Approach & phasing

Phase **by surface**; each phase independently buildable and testable, with the
riskiest (mobile, no git) isolated and snapshot-protected.

1. **Backend engine labels** — source of truth; smallest diff. Gate: `pytest`.
2. **Web** — relabel display sites; keep contract keys. Gate: `npm run build`,
   `npm run lint`, manual smoke.
3. **Mobile** — snapshot/branch the non-git directory first; rename labels +
   internal kebab/intent keys consistently. Gate: `tsc --noEmit`, `jest`,
   Expo render smoke.

Rejected alternatives: single big-bang PR (poor reviewability; mobile has no
rollback) and rename-by-token (breaks testability mid-stream).

## 8. Regression testing plan

- **Backend:** full `pytest`; update any label-asserting tests within the same
  phase.
- **Web:** `npm run build` + `npm run lint`; manual pass of Today, Meal Log
  (HomeScreen), Recipes, Meal Planner, Notifications.
- **Mobile:** `tsc --noEmit`, `jest` (with updated test assertions), Expo render
  of Today, Fuel Finder, Meal Plan, Notification settings.
- **Cross-cutting after each phase:**
  - *Leftover-vocab sweep:* grep that no "Recovery Snack/Meal", "Pre-Game
    Meal", "Pre-Training Meal", "Recovery Breakfast" remain in **display**
    positions.
  - *Contract-integrity check:* grep-confirm `window_key`/`window_type`/
    `category`/`category_key` values and recipe `category` keys are **unchanged**
    from `main`.

## 9. Open items to confirm at edit time
- Exact current line numbers in `window_engine_v2.py` (audit values are
  approximate; confirm before editing).
- Whether `pages/Today.jsx` renders any in-scope label or only the separate
  event-type vocabulary (leave the latter).
- That the mobile coach intent vocab is truly internal (no value is sent to /
  stored by the backend) before renaming it.
