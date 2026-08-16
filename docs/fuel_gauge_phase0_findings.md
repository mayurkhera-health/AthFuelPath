# Fuel Gauge — Phase 0 Audit Findings

**Status:** Phase 0 complete. **No code written.** Awaiting founder review before Phase 1.
**Date:** 2026-06-23
**Companion docs:** `fuel_gauge_design.md`, `fuel_gauge_implementation_plan.md`
**Repos audited:** backend `~/AthFuelPath`, frontend `~/AthFuelPath_Mobile/fuelup-mobile`

This doc resolves every `[VERIFY]` in the design and surfaces decisions that must be
made **before** Phase 1, because the live code differs from the design's assumptions in
several material ways.

---

## TL;DR — the five things that change the plan

1. **The Blueprint calc is already a clean pure function** — `calc_daily_targets(athlete, event_type, intensity)` in `api/services/nutrition_calc.py`. No DB, no LLM coupling. The rest-day adapter is a one-liner. ✅ Best-case outcome of Audit 1.

2. **Blueprint already computes EVENT-DAY targets too**, not just rest. `calc_daily_targets` takes `event_type ∈ {rest, practice, game, tournament, strength}` and an `intensity`. The design's premise — "rest = Blueprint, events = a brand-new engine" — is partly redundant. **Decision needed:** does the event-day engine *reuse* `calc_daily_targets` (recommended, keeps the two surfaces consistent on event days too) or reinvent protein/carb math?

3. **Blueprint produces 4 of 5 nutrients, and as RANGES not single numbers.** Protein ✅(range), Carbs ✅(range), Fluids ✅(oz, range), Calcium ✅(flat 1300mg), **Sodium ❌ (absent)**. Three sub-decisions fall out: range→single-number, oz vs ml, and what to show for rest-day sodium.

4. **The real `category_key` set is `{carb, balanced, recovery, hydrate}`** — NOT the `fuel_before/fuel_after/quick_snack/everyday` keys the design used illustratively. And `category_key` is **not currently in the Today payload** (engine generates it, `today_service` filters it out). The `hydrate` category is **nudge-only / non-tappable**.

5. **Un-confirm does not exist** and must be built (design §4.4 requires it). `window_logs` is upsert-only; there is no DELETE path.

Plus one memory correction: `db_migrations.run_all()` **does** now run (it was moved into the FastAPI `lifespan`). The **notification scheduler is still dead** (only wired to the ignored `@app.on_event("startup")`).

---

## AUDIT 1 — Blueprint calculation (HIGHEST PRIORITY)

**Where it lives:**
- Numeric calc (pure): `api/services/nutrition_calc.py` → `calc_daily_targets(athlete, event_type="rest", intensity=None)` and `calc_rmr(...)`.
- Per-athlete derived block: `api/routes/athletes.py` → `_computed_calculated(athlete)` calls `calc_daily_targets` for rest/practice/game/tournament/strength.
- Narrative only (no numbers): `api/services/claude_ai.py` → `prompt0_athlete_blueprint()`.
- Stored at athlete creation in `athletes.blueprint_json`; the **numbers are NOT in that JSON** — they're recomputed live in the `_calculated` block on `GET /api/athletes/:id/blueprint`.

**What it computes (verified against source, `nutrition_calc.py:116–158`):**

| Nutrient | Produced? | Shape | Units | Notes |
|---|---|---|---|---|
| Protein | ✅ | `protein_g_min` / `protein_g_max` | g | range, g/kg × weight, repositioned by intensity |
| Carbs | ✅ | `carbs_g_min` / `carbs_g_max` | g | range, scales most with event type |
| Fluids | ✅ | `hydration_oz_min` / `hydration_oz_max` | **oz** | fixed band per event type; does NOT vary by weight/sweat here |
| Calcium | ✅ | `calcium_mg` | mg | **flat 1300 for all** ages 9–17 (AAP). Not age-banded. |
| **Sodium** | ❌ | — | — | **Not computed anywhere in Blueprint.** Lives only in the weather/sweat path (Audit on weather below). |

Also computes (not gauge metrics): `total_calories`, `fat_g_min/max`, `iron_mg`, plus magnesium/vit-D in `_computed_calculated`.

**Inputs:** `weight_lbs`, `height_ft`, `height_in`, `gender`, `age` (athlete dict). RMR = **Everett MD 2025** (`11.1·kg + 8.4·cm − 537/340`), explicitly NOT Harris-Benedict. `intensity` (low/med/high) repositions within the carb/protein band. `event_type` selects the band.

**Stored vs live:** Narrative stored in `blueprint_json`; **numbers recomputed live** every GET. No stale-number risk. ✅

**Extractable?** Already extracted. `calc_daily_targets` is pure (no DB, no LLM, no FastAPI). The rest-day adapter (`compute_rest_day_targets`) is essentially `calc_daily_targets(athlete, "rest")` reshaped to the gauge dict. ✅

**Gap (per plan 0.1):** Blueprint computes **4 of 5** gauge nutrients — **sodium is missing**. Per the plan, the rest-day gauge shows only what Blueprint provides → `sodium_mg = None` on rest days. Documented behavior, not a bug.

---

## AUDIT 2 — Today payload (`today_service.py`)

- `build_today_view(athlete_id, conn, today=, force_v2=)` is the single assembler. ✅
- **Two call sites confirmed:** `api/routes/today.py:111` (`GET /:id/today`) and `api/routes/today.py:154` (capture refetch in `POST /:id/windows/:slot/capture`). Both must include the new `fuel_targets` block.
- Top-level payload keys: `athlete, today_event, today_events, day_type, readiness, windows, next_game, has_schedule, readiness_grid, streak`. `has_schedule` and `day_type` both present. ✅
- Per-window shape returned to client: `id, slot_name, display_label, eat_by_time, macro_focus, logged, sort_time, window_type, status, log{logged, method, photo_thumb_url, nutrient_status}`.
  - ⚠️ **`category_key` is generated by the engine but filtered out** at `today_service.py:~824–838`. The split needs it. Additive fix: include `category_key` in each window dict (also unblocks an existing frontend `WindowCard` that already reads `w.category_key`).
- **Confirm state:** table `window_logs` (`athlete_id, window_id TEXT, log_date, method, text, photo_url, thumb_url, audio_url, nutrient_status, logged_by, created_at`, `UNIQUE(athlete_id, window_id, log_date)`). Written by `record_window_capture()` via `INSERT … ON CONFLICT DO UPDATE` (upsert).
  - ⚠️ **Un-confirm does NOT exist** — no DELETE on `window_logs`, no client un-confirm. (There is a *separate* `confirmations` table with a DELETE in `fuel_report.py`, but it is not the Today path.) **Net-new work, required by design §4.4.**
- Status derivation: `assign_window_status()` — `logged=True → "done"`, first unlogged → `"next"`, rest → `"upcoming"`. Honors the Window Status Invariant (time never marks done). ✅

---

## AUDIT 3 — Athlete profile

- Schema (`db/setup.py`): `weight_lbs REAL` (lbs), `height_ft INTEGER`, `height_in REAL`, `age INTEGER`, `gender TEXT`, `position TEXT`, `competition_level TEXT` (`recreational|competitive_club|elite_club`), `sweat_profile TEXT`, `allergies`, `dietary_restrictions`, `supplement_use`. **All imperial; calc converts lbs→kg internally.**
- **No `season_phase` or equivalent exists.** Confirmed. ✅ (net-new)
- Models (`api/models.py`): `AthleteCreate` and `AthleteResponse`. **There is no `AthleteUpdate`** — `PUT /api/athletes/:id` reuses `AthleteCreate`. (The plan's "EventCreate/EventUpdate/EventResponse" was a misnomer — the right targets are `AthleteCreate` + `AthleteResponse`.) Both need `season_phase: Optional[str]`.
- Migration pattern (`api/services/db_migrations.py`): idempotent PRAGMA-guarded `ADD COLUMN`, e.g. `_add_intensity_to_events`. `run_all()` is invoked from the `lifespan` handler in `api/main.py:21` → **migrations run on deploy.** ✅ New: `_add_season_phase_to_athletes()` defaulting `'in_season'`, registered in `run_all()`.
- Frontend (`app/(app)/settings/edit-profile.tsx`): saves via `PUT /api/athletes/:id` spreading the athlete object. Reusable single-select `PillPicker` exists in `components/onboarding/AthleteFields.tsx` — ideal for the season-phase selector. **Use the design's 3 values** (`in_season`/`off_season`/`postseason`), not the 4 the sub-audit guessed.

---

## AUDIT 4 — Window engine (`window_engine_v2.py`)

- Live engine confirmed: `event_relative_windows_enabled()` reads `EVENT_RELATIVE_WINDOWS` (we know it's `true` in Fly secrets); `force_v2` also forces it. ✅
- **Real `category_key` set (exhaustive): `{ "carb", "balanced", "recovery", "hydrate" }`** — only four coarse values, mapped from the window slots:
  - `carb` → `pre_event_meal`, `top_up_snack`, `quick_morning_snack`, `between_games`
  - `recovery` → `fuel_after_primary`, `fuel_after_second`, `proper_breakfast_after`, `refuel_ready`
  - `balanced` → `everyday_breakfast/lunch/snack/dinner`
  - `hydrate` → `fuel_during` — **nudge-only, `is_tappable=False`** (never a confirm tap)
- Timing fields per window: `open_time`, `close_time` (24h `HH:MM`), `time_display` (range), `sort_time`. Floor 06:30. Sufficient for the contribution split and for notification triggers.
- **Tappable vs not:** every category is tappable **except `hydrate`/`fuel_during`**.

⚠️ **Design implication:** the contribution-weight table keys on these 4 real categories (not the illustrative ones). And because `hydrate` is non-confirmable, any creditable weight assigned to it could never be filled → gauges couldn't reach ~100%. **Recommendation:** only **tappable** windows carry creditable weight; normalize each nutrient across tappable windows so confirming all of them reaches ~100%. (Fluid/sodium "credit" for the during-event nudge is folded into the recovery window.)

---

## AUDIT 5 — Notifications

- **Dormant, ~80% built.** `NOTIFICATION_DRY_RUN` (`notification_service.py:39`) default `false`; gates the actual Expo push call.
- **Scheduler is dead:** `run_notification_tick()` (sound, 15-min interval) is registered **only** in `@app.on_event("startup")` (`main.py:76`), which Starlette **ignores** because a `lifespan` is set. So it has never run in prod. Reviving = move the scheduler into the `lifespan` block + delete the dead handlers (~10 lines).
- Delivery: **Expo push API** (`exp.host`) via `send_expo_push()`; `expo_push_tokens` table (with `timezone`). Legacy `push_subscriptions`/VAPID exists but unused.
- Frontend: `services/notifications.ts` `registerTokenIfPermitted()` exists and sends timezone, but **is not called on app launch** (only from the Settings toggle) → most installed athletes have **no token**. Prefs live in AsyncStorage, **not synced to backend**. `EXPO_PROJECT_ID` matches `app.json`. ✅
- **Feasibility:** the scheduler fix itself is ~2 hrs, but real-device testing needs a dev build (Expo Go can't receive push on SDK 54), token-on-launch wiring, and dietitian copy sign-off. **Recommendation: ship gauges first; notifications as a fast-follow** (matches design open-question #4 and the rollout note "notifications do NOT gate the gauge release").

---

## Memory / status correction

Prior session memory said `run_all()` migrations *and* the notification scheduler both never ran (dead `@app.on_event`). **Updated reality:** `run_all()` was moved into `lifespan` and now runs on deploy; **only the notification scheduler remains dead.** (Memory file updated.)

---

## Decisions required before Phase 1 (founder sign-off)

| # | Decision | Recommendation |
|---|---|---|
| **D1** | Event-day engine: reuse `calc_daily_targets(event_type, intensity)` as its protein/carb core (then layer season_phase modifier + weather sodium/fluids + multi-event load + window split), or build standalone math? | **Reuse it.** Keeps Today↔Blueprint consistent on event days too; the "new" coefficients in `fueling_targets.py` become season-phase/weather *modifiers* + the split table, not a parallel macro model. |
| **D2** | Blueprint returns **ranges**; the gauge needs one target. Use min, midpoint, or max? | **PENDING_CLINICAL** — placeholder = **max** ("target to reach"), single knob in `fueling_targets.py`. Dietitian confirms. |
| **D3** | Fluids are **oz** in Blueprint; design says ml. | **Keep oz** end-to-end (matches existing code + UI); sodium/calcium in mg. Avoids a conversion-rounding mismatch between surfaces. |
| **D4** | **Sodium absent** from Blueprint → rest-day sodium gauge. | Rest day: `sodium_mg = None` (gauge hidden/greyed). Event day: from `calc_sweat_output()` (weather). Documented gap. |
| **D5** | Calcium is **flat 1300mg**, not age-banded. Test plan T1 expects "14yo vs 17yo differ." | Document calcium as flat & load-independent; **revise the T1 calcium-age test** to assert flatness — OR dietitian supplies age bands in `fueling_targets.py` (event-day only; rest-day still 1300 from Blueprint). Flag. |
| **D6** | `hydrate`/`fuel_during` is non-tappable → can't be credited. | Normalize creditable weight across **tappable** windows only; fold during-event fluid/sodium into recovery. |
| **D7** | Notifications in v1 or fast-follow? | **Fast-follow.** Gauges don't gate on it; needs dev build + copy sign-off. |

**No Phase 1 code will start until these are confirmed — especially D1, since the whole event-day path hinges on it.**
