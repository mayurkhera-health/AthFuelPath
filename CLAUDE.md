# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ Backend runtime cutover (2026-08-20) — READ BEFORE TOUCHING DEPLOY ANYTHING

`main` was merged with the `migration/postgres-cloud-run` branch on 2026-08-20.
As of that merge, **`main` requires PostgreSQL/Cloud SQL to boot at all** —
`api/database.py` has no SQLite fallback anymore (the SQLite code path was
removed, not just disabled). The real, live deploy target is now **Cloud Run**
(`athfuelpath-api`, project `fuelup-500318`, region `us-west1`), not Fly.io.

**Fly.io (`fuelup-youth`) is now a frozen rollback snapshot, not a deploy
target.** It's still running the pre-cutover SQLite-based code and is
intentionally left untouched as a safety net. Do **not** deploy current `main`
to it — `api/database.py` will fail loudly on startup (no Postgres env/secrets
configured there), crash-looping the live app.

- If Fly ever needs to be redeployed for real, use the tag
  `fly-sqlite-last-known-good` (the last commit before this cutover merge) —
  **not** current `main`.
- The GitHub Actions auto-deploy-to-Fly-on-push-to-main workflow
  (`.github/workflows/fly-deploy.yml`) has been **deleted** for exactly this
  reason — it would otherwise have auto-triggered a Fly deploy of
  Postgres-only code on the very push that merged this cutover. If you're
  reading this because that workflow got re-added, stop and reconsider before
  pushing to `main`.
- Real prod data (parents, athletes, events, etc.) was migrated from Fly's
  SQLite database to Cloud SQL via `db/migrate_sqlite_data.py` — Cloud SQL is
  the live source of truth now, not Fly's SQLite volume.
- Known open item: `POST /api/parents/login` and `POST /api/auth/login` are
  still email-only (no password/OTP) — see `docs/cloud-run-security-audit.md`.
  This is real, live, unresolved risk on a public endpoint with real users'
  data — not merely documented for later.

## Branch & Deployment Rules — historical (pre-cutover, Fly.io-era)

Everything below this line describes the Fly.io deploy process as it worked
**before** the 2026-08-20 cutover above. Kept for reference (e.g., if
`fly-sqlite-last-known-good` is ever actually redeployed) — do not follow it
against current `main`.

### Single source of truth
- `main` is the ONLY branch for backend production deployments
- All backend fixes, features, and hotfixes must be applied to `main`
- Never deploy from `AthFuelPath-Admin`, a worktree, or any other branch

### AthFuelPath-Admin
- `AthFuelPath-Admin` is NOT a deployment branch
- Do not apply fixes to `AthFuelPath-Admin` directly
- If a fix exists on `AthFuelPath-Admin` that is needed in production, cherry-pick it onto `main` — do not switch deployment branches
- Never run `flyctl deploy` from `AthFuelPath-Admin` or any worktree based on it

### Deployment command
Always deploy from the main worktree via the guarded wrapper (checks you're on
`main`, a clean tree, and reminds you about the `PERFORMANCE_PLATE_ENABLED` flag —
the plate ships DARK and deploy alone does NOT enable it):
```bash
cd ~/AthFuelPath-main
./scripts/deploy.sh
```
Raw command it wraps (do not run directly unless the wrapper is unavailable):
`flyctl deploy --app fuelup-youth`

### Before every deploy, confirm:
1. You are on `main` (`git branch` shows `* main`)
2. All intended fixes are committed to `main`
3. `git status` is clean
4. `tsc --noEmit` passes (for mobile changes)

### Why this rule exists
- v177 (Jun 30 2026) was deployed from `AthFuelPath-Admin` instead of `main`
- This broke parent signup because `/parents/exists` and `/onboarding/complete` only existed on `main`
- One deployment branch only — always `main`

## Commands

### Backend
```bash
source venv/bin/activate
python db/setup.py                          # initialize SQLite database (run once)
uvicorn api.main:app --reload --port 8000   # start FastAPI dev server
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Vite dev server (reads VITE_API_URL from frontend/.env.local)
npm run build    # production build to frontend/dist/
npm run lint     # ESLint
```

### Deployment
See the cutover warning at the very top of this file. Fly.io is a frozen
rollback snapshot as of 2026-08-20 — the commands below are historical
(pre-cutover) and only apply to the `fly-sqlite-last-known-good` tag, never
to current `main`.
```bash
fly deploy -a fuelup-youth                          # (historical — see warning above)
fly ssh console -a fuelup-youth -C "python db/setup.py"  # re-init DB on server
fly logs -a fuelup-youth                            # tail live logs
```

There is no CI auto-deploy anymore — `.github/workflows/fly-deploy.yml` (which
deployed to Fly.io on every push to `main`) was deleted as part of the
2026-08-20 cutover, since it would otherwise auto-deploy Postgres-only code to
Fly's SQLite-only environment on every future push to `main`.

Real deploy path now: Cloud Run (`athfuelpath-api`, project `fuelup-500318`,
region `us-west1`) via `gcloud builds submit` + `gcloud run services update`.

## Architecture

### Overview
Single-VM deployment on Fly.io (region: `sjc`). Uvicorn serves both the FastAPI backend and the compiled React frontend as static files from the same process on port 8000.

```
api/main.py            — FastAPI app, routes registered, StaticFiles mounted last at /
api/routes/            — one file per domain (parents, athletes, events, nutrition,
                         meals, recipes, analysis, reports, notifications, meal_plans)
api/models.py          — all Pydantic request/response models
api/database.py        — get_conn() returns a sqlite3 connection to DB_PATH env var
api/services/          — business logic (nutrition_calc, claude_ai, meal_timing,
                         recipe_db, weather)
db/setup.py            — creates all SQLite tables; re-run is safe (CREATE IF NOT EXISTS)
frontend/src/          — React SPA (no router library; App.jsx uses useState for views)
frontend/.env.local    — VITE_API_URL=http://localhost:8000 (dev only, gitignored)
```

### Database
Raw SQLite via `api/database.py`. No ORM. All queries use `conn.execute()` with `?` parameters. Tables: `parents`, `athletes`, `events`, `meal_logs`, `push_subscriptions`, `meal_plans`, `daily_targets`. Django (`athfuelpathy/`, `manage.py`) is present in the repo but **not used** by the running application — it is an artifact of the initial scaffold.

### API → Frontend contract
All API routes use the `/api/` prefix. The React frontend sets `const API = import.meta.env.VITE_API_URL ?? ""` at the top of each screen file, so all fetch calls are `${API}/api/...`. In production `VITE_API_URL` is unset and calls are same-origin. The FastAPI `StaticFiles` mount at `/` serves `frontend/dist/index.html` for all non-API paths, enabling client-side navigation.

### Nutrition science layer
`api/services/nutrition_calc.py` computes daily targets (calories, carbs, protein, fat, hydration, iron, calcium) from athlete weight/age/gender and event type using a fixed formula (Everett 2025 RMR, never Harris-Benedict). `api/services/claude_ai.py` wraps Claude Sonnet (`claude-sonnet-4-6`) with a strict system prompt encoding the same science framework and always returns JSON. The system prompt in `claude_ai.py` is the authoritative source for all science rules — do not contradict it.

### Meal timing
`api/services/meal_timing.py` maps event type + start time to a timed protocol list (pre-game meal, pre-game snack, halftime, 30-min recovery window, etc.). `api/routes/meal_plans.py` maps each event type to a set of named meal slots (`SLOTS_BY_EVENT`) and maps slots to recipe timing categories (`SLOT_TO_CATEGORY`).

### Frontend screens
`App.jsx` owns the top-level view state (`login → onboarding → dashboard`). `Dashboard.jsx` renders `AppShell` with a selected athlete and tab. Each tab is a standalone screen component. `Blueprint.jsx` renders the athlete's AI-generated nutrition blueprint. There is no client-side routing library.

### Push notifications
`api/routes/notifications.py` stores Web Push subscriptions (`push_subscriptions` table) and serves the VAPID public key — used by the legacy web frontend's `frontend/src/NotificationsScreen.jsx` + `notificationService.js` (browser service worker at `frontend/public/sw.js`). **Correction (2026-07-26): `pywebpush` is never actually imported or called anywhere in the codebase** — subscribing/storing/toggling prefs all work, but nothing ever sends a Web Push through them. This is separate from the mobile app's Expo push (`expo_push_tokens` table, `notification_service.py`, `POST /expo-token`), which does actually send.

## Test suite baseline — `feat/fueliq` (deterministic, established 2026-07-14)

Run: `python3 -m pytest tests/ --tb=no -q` from `~/AthFuelPath-main`

**Baseline result: 19 failed / 597 passed / 2 errors** (~84–92 s)

Verified identical across 3 consecutive runs.  DB isolation was fixed on 2026-07-14
(see `tests/conftest.py`): each test module gets its own named in-memory SQLite DB,
the APScheduler background thread is suppressed for tests (prevents SQLITE_LOCKED
races), and three Phase 5 Fuel IQ test assertions were updated to match the new
level count (4→5 levels, `level_name` field) and badge count (6→8 badges).
Commit `cdd31e1` message incorrectly says "two Fuel IQ tests" — it was three
(`test_hub_returns_baseline_progress_when_enabled`, `test_badges_lists_all_defined_badges_locked_until_earned`,
`test_list_badges_returns_every_defined_badge`).

When adding Phase work on this branch, diff against this list. A test not in this list
that starts failing is a regression introduced by the new work and must be fixed before
the phase is considered done.

### Pre-existing FAILED tests (19)

```
tests/test_fuel_gauge.py::test_event_day_has_all_five_metrics
tests/test_fuel_gauge.py::test_event_day_split_excludes_everyday_and_reaches_100
tests/test_fuel_gauge.py::test_flag_off_payload_is_byte_identical_to_production
tests/test_fuel_gauge.py::test_fuel_targets_shape_when_flag_on
tests/test_fuel_gauge.py::test_split_unknown_category_contributes_zero_and_logs
tests/test_fueliq_daily_challenge_route.py::test_daily_challenge_verdict_flow_end_to_end  ← see isolation note below
tests/test_notification_service.py::TestSendExpoPush::test_different_recipient_is_independent
tests/test_notification_service.py::TestSendNotificationGuarded::test_duplicate_send_returns_false_and_does_not_push
tests/test_notification_service.py::TestSendNotificationGuarded::test_first_send_returns_true_and_calls_push
tests/test_plate_route.py::test_window_returns_plate_and_options
tests/test_recipe_generator.py::test_generate_recipe_agent_picks_from_library
tests/test_recipe_generator.py::test_generate_recipe_falls_back_on_invalid_agent_id
tests/test_recipe_generator.py::test_get_valid_recipes_returns_halftime_options
tests/test_today_service.py::test_mission_items_iron_critical_for_girls
tests/test_window_templates.py::test_early_morning_game_6am
tests/test_window_templates.py::test_evening_practice_7_30pm
tests/test_window_templates.py::test_max_taps_not_exceeded
tests/test_window_templates.py::test_tournament_close_gap
tests/test_window_templates.py::test_tournament_wide_gap
```

### Pre-existing ERROR tests (2) — intra-module ordering issue

```
tests/test_fueliq_daily_challenge_route.py::test_daily_challenge_verdict_404_when_nothing_scheduled
tests/test_fueliq_daily_challenge_route.py::test_daily_challenge_verdict_does_not_appear_in_fueliq_hub_score
```

### Known isolation issue — `test_fueliq_daily_challenge_route`

Three tests in `tests/test_fueliq_daily_challenge_route.py` fail when run as a module
but pass when run as individual tests (`pytest path::test_name`):
- `test_daily_challenge_verdict_flow_end_to_end` — FAILS in module run, PASSES individually
- `test_daily_challenge_verdict_404_when_nothing_scheduled` — ERROR in module run, PASSES individually
- `test_daily_challenge_verdict_does_not_appear_in_fueliq_hub_score` — ERROR in module run, PASSES individually

Root cause: intra-module ordering dependency within `test_fueliq_daily_challenge_route.py`
(an earlier test in the file leaves DB state that later tests do not expect). Not
cross-module contamination — the module-scoped DB isolation fix resolved cross-module
issues. Not urgent — fix when the daily challenge tests need to be extended. Do not
count these as Phase regressions.
