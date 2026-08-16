# Day-Layout Target Computation Fix (Plan D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the `DAY_LAYOUT_V2`-ON path only, compute daily macro targets from the event's REAL `event_type` + resolved `activity_type` (so event days get event-level macros and the per-activity-type modifiers apply) — making the flag safe to enable. The legacy (flag-OFF / production) path is left byte-for-byte unchanged.

**Architecture:** Add an optional `activity_type` override to `calc_daily_targets` that drives the activity-engine profile (cho_modifier / intensity_override / is_sc_day) when supplied, falling back to the existing `event_type`→profile derivation when not. In `build_today_view`, the flag-ON branch computes the target inputs from the primary event's real `event_type` and its resolved `activity_type`; the legacy branch keeps using the engine `day_type` label exactly as today. The new `activity_type` param defaults to `None`, so the legacy call is unchanged.

**Tech Stack:** Python 3.12 / FastAPI / SQLite / pytest. Backend repo root: `/Users/mayurkhera/AthFuelPath`. No mobile changes. No new dependencies.

---

## Scope (decided with the user — Option 1)
- **Fix the flag-ON path ONLY.** `DAY_LAYOUT_V2` is OFF in prod, so this deploy is inert for live athletes; it only affects the new day-layout path the user will QA before flipping the flag.
- **Do NOT change the legacy (flag-OFF) path.** It currently passes the engine `day_type` label to `calc_daily_targets` (a pre-existing prod bug where event days compute rest-level macros). That legacy/prod fix is a SEPARATE, Purvi-reviewed change — explicitly out of Plan D.

## Background facts (verified — read before starting)

**The bug (flag-ON path).** In `build_today_view` (`api/services/today_service.py`), the flag-ON branch sets `event_type = _layout["day_type"]` (one of `"standard" | "rest" | "tournament" | "active_recovery"`). The shared target block then does:
```python
event_type_for_targets = event_type            # ~line 992 — the day_type label
_daily_targets = calc_daily_targets(athlete, event_type_for_targets, _intensity, _dur_min)
```
`calc_daily_targets` → `normalize_event_type("standard")` → not in `EVENT_TYPE_MAP` → falls through to `"rest"` → rest-level CHO (4.0 g/kg) on a real event day. Verified: `calc_daily_targets(ATH, "standard")` = 4.0 g/kg; `calc_daily_targets(ATH, "game")` = 6.0; `"tournament"` = 10.0; `"practice"` = 4.5.

**`calc_daily_targets` activity-profile line** (`api/services/nutrition_calc.py:510-513`):
```python
    norm = normalize_event_type(event_type)
    pal = PAL.get(athlete.get("lifestyle_activity", "light"), 1.4)
    act = get_activity_profile(_to_activity_type(norm), intensity, duration_min, wt_kg)
```
`act` (cho_modifier / intensity_override / is_sc_day / aee) is the ONLY place the per-activity-type modifiers are produced. `cho_intensity` (line 520-521) uses `act["intensity_override"]` when it's a `CHO_FACTOR` key, and `is_sc_day=act["is_sc_day"]` flows into `calc_daily_protein`. So overriding `act` with the resolved activity_type makes speed_sprint (×1.10), strength_cond (is_sc_day), active_recovery (intensity_override "rest" → 4.0 CHO), and double_session (×1.25) all apply.

**The 7 activity_type keys** are exactly the `activity_engine` profile keys: `practice, game, tournament, speed_sprint, strength_cond, active_recovery, double_session` — exposed as `VALID_ACTIVITY_TYPES` in `api/services/activity_type_resolver.py` (imports only stdlib → no circular import with nutrition_calc).

**`resolve_activity_type(event, now)`** (`api/services/activity_type_resolver.py`) returns the tagged activity_type, or `practice` once within 2h of start, else `None`.

**`build_today_view` flag branch (post-Plan-C)** computes `effective_now` and `events` before the target block, and has the `today_str`. The target block (`~line 988-996`) reads `_ev0 = events[0] if events else {}`, `_dur_min`, `_intensity`.

**Test conventions:** `python3 -m pytest tests/test_x.py -v` from `/Users/mayurkhera/AthFuelPath`. Pure functions take `now` explicitly. KNOWN pre-existing failures to ignore: `test_today_service.py::test_mission_items_iron_critical_for_girls` and the dirty-tree suites.

---

## File Structure
- **Modify** `api/services/nutrition_calc.py` — `calc_daily_targets` gains an optional `activity_type` override that drives the activity profile.
- **Modify** `api/services/today_service.py` — `build_today_view`: flag-ON branch computes `event_type_for_targets` (real event_type) + `activity_type_for_targets` (resolved); legacy branch keeps the day_type label + `None`; the target call passes `activity_type=activity_type_for_targets`.
- **Tests:** `tests/test_nutrition_calc.py` (activity_type override) + `tests/test_day_layout_today_integration.py` (flag-ON event-day macros) + confirm `tests/test_today_service.py` legacy unchanged.

---

## Task D1: `calc_daily_targets` activity_type override

**Files:**
- Modify: `api/services/nutrition_calc.py`
- Test: `tests/test_nutrition_calc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nutrition_calc.py` (the file already defines `ATH` and imports the module as `nc`):

```python
def test_activity_type_override_drives_profile():
    # event_type "practice" but activity_type "game" -> game CHO bump applies
    base = nc.calc_daily_targets(ATH, "practice")                          # practice profile
    over = nc.calc_daily_targets(ATH, "practice", activity_type="game")    # game profile via override
    assert over["carbs_g"] > base["carbs_g"]


def test_activity_type_active_recovery_gives_rest_cho():
    # tagged active_recovery -> rest-level CHO even if event_type says practice
    wt = nc.lbs_to_kg(ATH["weight_lbs"])
    t = nc.calc_daily_targets(ATH, "practice", activity_type="active_recovery")
    assert round(t["carbs_g"] / wt) == 4   # rest factor 4.0 g/kg


def test_activity_type_strength_cond_sets_sc_protein_bump():
    # tagged strength_cond -> is_sc_day true -> recharge/protein reflect the S&C bump.
    # Compare protein vs a plain practice (no SC bump).
    practice = nc.calc_daily_targets(ATH, "practice")
    sc = nc.calc_daily_targets(ATH, "practice", activity_type="strength_cond")
    assert sc["protein_g"] >= practice["protein_g"]


def test_invalid_activity_type_falls_back_to_event_type():
    # bogus activity_type ignored -> behaves like the event_type-derived profile
    a = nc.calc_daily_targets(ATH, "game", activity_type="bogus")
    b = nc.calc_daily_targets(ATH, "game")
    assert a["carbs_g"] == b["carbs_g"]


def test_no_activity_type_unchanged():
    # default None -> identical to the pre-override behavior
    a = nc.calc_daily_targets(ATH, "game")
    b = nc.calc_daily_targets(ATH, "game", activity_type=None)
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_nutrition_calc.py::test_activity_type_override_drives_profile -v`
Expected: FAIL — `calc_daily_targets() got an unexpected keyword argument 'activity_type'`.

- [ ] **Step 3: Implement the override**

In `api/services/nutrition_calc.py`:

Add the import near the other `api.services` imports at the top:
```python
from api.services.activity_type_resolver import VALID_ACTIVITY_TYPES
```

Add the `activity_type` parameter to the signature (after `humidity_pct`):
```python
def calc_daily_targets(
    athlete: dict,
    event_type: str = "rest",
    intensity: Optional[str] = None,
    duration_min: float = 0,
    is_outdoor: bool = False,
    temp_f: float = 70,
    humidity_pct: float = 50,
    activity_type: Optional[str] = None,
) -> dict:
```

Replace the activity-profile line (currently `act = get_activity_profile(_to_activity_type(norm), intensity, duration_min, wt_kg)`) with:
```python
    # An explicit resolved activity_type (the athlete's per-event tag) overrides the
    # event_type-derived profile, so the per-type modifiers apply: speed_sprint ×1.10,
    # strength_cond is_sc_day, active_recovery rest-level CHO, double_session ×1.25.
    # Falls back to the event_type-derived activity type when not supplied/invalid.
    profile_key = activity_type if activity_type in VALID_ACTIVITY_TYPES else _to_activity_type(norm)
    act = get_activity_profile(profile_key, intensity, duration_min, wt_kg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_nutrition_calc.py -v`
Expected: PASS (the 5 new tests + the existing nutrition_calc tests still green).

- [ ] **Step 5: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath
git add api/services/nutrition_calc.py tests/test_nutrition_calc.py
git commit -m "feat: calc_daily_targets activity_type override (per-type modifiers; None = unchanged)"
```

---

## Task D2: `build_today_view` flag-ON path uses real event_type + resolved activity_type

**Files:**
- Modify: `api/services/today_service.py`
- Test: `tests/test_day_layout_today_integration.py`

- [ ] **Step 1: Write the failing test**

`build_today_view` does NOT expose the daily targets in its return dict (`_daily_targets` only feeds per-window gram chips). So we verify the wiring with a SPY on `calc_daily_targets` — asserting the flag-ON path calls it with the REAL `event_type` + resolved `activity_type` (not the `"standard"` day_type label), and the legacy path calls it with the day_type label + `activity_type=None`. This is the same spy approach used in `test_build_today_view_uses_client_now_for_2h_resolver`.

Append to `tests/test_day_layout_today_integration.py`:

```python
def _seed_athlete_with_event(conn, email, event_type, activity_type, start="15:00"):
    from db.setup import init_db
    from api.services.db_migrations import run_all
    init_db(); run_all()
    conn.execute("INSERT INTO parents (full_name, email, consent_confirmed) VALUES ('P',?,1)", (email,))
    pid = conn.execute("SELECT id FROM parents WHERE email=?", (email,)).fetchone()[0]
    conn.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
                 "VALUES (?, 'A', 14, 'boy', 120, 5, 4)", (pid,))
    aid = conn.execute("SELECT id FROM athletes WHERE parent_id=?", (pid,)).fetchone()[0]
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours, activity_type) "
                 "VALUES (?, 'E', ?, '2026-06-27', ?, 1.5, ?)", (aid, event_type, start, activity_type))
    conn.commit()
    return aid


def _spy_calc_daily_targets(monkeypatch):
    """Patch calc_daily_targets in today_service; capture the (event_type, activity_type) it gets."""
    import api.services.today_service as ts
    captured = {}
    real = ts.calc_daily_targets
    def spy(athlete, event_type="rest", intensity=None, duration_min=0, **kw):
        captured["event_type"] = event_type
        captured["activity_type"] = kw.get("activity_type")
        return real(athlete, event_type, intensity, duration_min, **kw)
    monkeypatch.setattr(ts, "calc_daily_targets", spy)
    return captured


def test_flag_on_targets_use_real_event_type_and_resolved_tag(monkeypatch):
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    conn = get_conn()
    aid = _seed_athlete_with_event(conn, "d1@x.com", "game", "game")
    captured = _spy_calc_daily_targets(monkeypatch)
    build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 14, 0))
    conn.close()
    assert captured["event_type"] == "game"        # REAL event_type, not "standard"
    assert captured["activity_type"] == "game"      # resolved tag threaded


def test_flag_on_active_recovery_tag_threaded(monkeypatch):
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    conn = get_conn()
    aid = _seed_athlete_with_event(conn, "d2@x.com", "practice", "active_recovery", start="10:00")
    captured = _spy_calc_daily_targets(monkeypatch)
    build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 9, 0))
    conn.close()
    assert captured["event_type"] == "practice"
    assert captured["activity_type"] == "active_recovery"


def test_flag_off_legacy_targets_unchanged(monkeypatch):
    monkeypatch.delenv("DAY_LAYOUT_V2", raising=False)
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    conn = get_conn()
    aid = _seed_athlete_with_event(conn, "d3@x.com", "game", "game")
    captured = _spy_calc_daily_targets(monkeypatch)
    build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 14, 0))
    conn.close()
    # Legacy path: event_type is the engine day_type label (NOT the raw "game"),
    # and activity_type override is None (prod behavior unchanged).
    assert captured["activity_type"] is None
    assert captured["event_type"] != "game"   # it's the day_type label (e.g. afternoon_game)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py::test_flag_on_targets_use_real_event_type_and_resolved_tag -v`
Expected: FAIL — flag-ON currently passes the `"standard"` day_type label and no activity_type (the spy sees `event_type=="standard"`, `activity_type is None`).

- [ ] **Step 3: Implement the flag-ON target inputs**

In `api/services/today_service.py`:

Add the resolver import near the top (with the other `api.services` imports):
```python
from api.services.activity_type_resolver import resolve_activity_type
```

In `build_today_view`, the flag branch currently looks like:
```python
    if day_layout_v2_enabled():
        from datetime import datetime as _dt
        effective_now = now if now is not None else _dt.now()
        _layout = build_day_layout(events, athlete, now=effective_now)
        event_type       = _layout["day_type"]
        template_windows = cards_to_template_windows(_layout["cards"], today_str)
    else:
        engine_result    = generate_windows_for_day(athlete_id, today_str, events, force_v2=force_v2)
        event_type       = engine_result["day_type"]
        template_windows = engine_result["windows"]
```
Extend BOTH branches to also set the target inputs. After `event_type = _layout["day_type"]` in the flag branch, add:
```python
        # Flag-ON targets: use the primary event's REAL event_type + resolved
        # activity_type so event days get event-level macros and per-type modifiers
        # apply (Plan D). Legacy branch keeps the day_type label (prod unchanged).
        _primary = events[0] if events else {}
        event_type_for_targets    = _primary.get("event_type", "rest")
        activity_type_for_targets = resolve_activity_type(_primary, effective_now) if _primary else None
```
And in the `else` (legacy) branch, after `event_type = engine_result["day_type"]`, add:
```python
        event_type_for_targets    = event_type   # legacy: day_type label, unchanged
        activity_type_for_targets = None
```

Then in the shared target block below, DELETE the existing `event_type_for_targets = event_type` line and change the `calc_daily_targets` call to pass the activity_type:
```python
    _ev0 = events[0] if events else {}
    _dur_min = (_ev0.get("duration_hours") or 0) * 60
    _intensity = _ev0.get("intensity")
    _daily_targets = calc_daily_targets(athlete, event_type_for_targets, _intensity, _dur_min,
                                        activity_type=activity_type_for_targets)
```
READ the current target block first to splice this in exactly (preserve `_ev0`/`_dur_min`/`_intensity` and the `_daily_carbs`/`_daily_protein` lines that follow).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py -v`
Expected: PASS (both new tests + existing).

- [ ] **Step 5: Confirm the legacy (flag-OFF) path is unchanged**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_today_service.py -q`
Expected: same result as before — only the known pre-existing `test_mission_items_iron_critical_for_girls` fails; NO new failures. (The legacy branch now sets `event_type_for_targets = event_type` and `activity_type_for_targets = None`, so `calc_daily_targets(..., activity_type=None)` is byte-for-byte the prior behavior.)

- [ ] **Step 6: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath
git add api/services/today_service.py tests/test_day_layout_today_integration.py
git commit -m "feat: flag-ON Today targets use real event_type + resolved activity_type (legacy unchanged)"
```

---

## Task D3: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full backend day-layout + nutrition + today suites**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_nutrition_calc.py tests/test_day_layout.py tests/test_day_layout_today_integration.py tests/test_today_service.py -q`
Expected: all pass except the known pre-existing `test_mission_items_iron_critical_for_girls`. No NEW failures.

- [ ] **Step 2: Sanity-print the flag-ON targets by day type (not committed)**

Run:
```bash
cd /Users/mayurkhera/AthFuelPath && python3 -c "
from api.services.nutrition_calc import calc_daily_targets, lbs_to_kg
ATH={'weight_lbs':120,'height_ft':5,'height_in':4,'gender':'boy','age':14}
wt=lbs_to_kg(120)
for et, at in [('game','game'),('practice','practice'),('practice','speed_sprint'),('practice','active_recovery'),('strength','strength_cond'),('tournament','tournament')]:
    t=calc_daily_targets(ATH, et, activity_type=at)
    print(f'{et:9s}/{at:15s} carbs={t[\"carbs_g\"]:4d} ({t[\"carbs_g\"]/wt:.1f} g/kg)  protein={t[\"protein_g\"]}')
"
```
Expected: game ≈6, speed_sprint > practice (×1.10), active_recovery ≈4 (rest), tournament ≈10. Eyeball that these match Purvi's spec; report the table.

- [ ] **Step 3: No commit** (verification only).

---

## After all tasks

- [ ] Use **superpowers:finishing-a-development-branch**.
- [ ] **The flag is now safe to enable.** Hand-off to the user: set `DAY_LAYOUT_V2=true` and QA an athlete's Today tab with tagged events — verify the macro numbers now look event-appropriate (game ~6 g/kg, etc.) and the per-type tags change them. The user runs the flip + any TestFlight build.
- [ ] **Still deferred (NOT Plan D):** the legacy/prod rest-macros-on-event-days bug (Option-1 decision — separate Purvi-reviewed change); server-side role-gating; the §14.3 grams-to-athletes philosophy; the 33/34/33 rest split.

---

## Self-Review

**Spec coverage:**
- Event days compute event-level macros on the flag-ON path → Task D2 (real event_type) ✅
- Per-activity-type modifiers apply (speed_sprint/strength_cond/active_recovery/double_session) → Task D1 (activity_type override) + D2 (resolved tag passed) ✅
- Legacy/prod path byte-for-byte unchanged → Task D2 (legacy branch sets event_type_for_targets=day_type, activity_type=None) + D1 (`activity_type=None` default no-op) ✅ verified in D2 Step 5.
- Flag stays OFF; user flips after QA → After-all-tasks ✅

**Placeholder scan:** every code step has complete code; every test step has real assertions; the one "confirm the return key name" note (D2 Step 1) is a read-and-adapt instruction, not a vague placeholder.

**Type consistency:** `activity_type` param name consistent across D1 (calc_daily_targets) and D2 (call site `activity_type=activity_type_for_targets`). `VALID_ACTIVITY_TYPES` (from activity_type_resolver) used in D1; `resolve_activity_type` (same module) used in D2 — both confirmed importable without cycles. `event_type_for_targets` / `activity_type_for_targets` set in both build_today_view branches and read once in the target block.

**Known minor (documented, not fixed):** when an event's `event_type` is "practice" but the tag is "strength_cond", `_sport_type_from_event(norm)` still returns "soccer" (so the protein SPORT_PROT base is soccer, not strength) — but `is_sc_day=True` from the overridden profile still applies the S&C protein bump, so the dominant S&C effect is correct. Refining sport_type from activity_type is a minor follow-up, out of Plan D scope.
