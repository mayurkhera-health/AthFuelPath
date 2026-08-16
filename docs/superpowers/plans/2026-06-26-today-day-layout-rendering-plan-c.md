# Today-Tab Day-Layout Rendering (Plan C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `DAY_LAYOUT_V2` flag-ON path render correctly on the athlete Today tab — fix the 2-hour resolver timezone, surface the Keep-Going oz/packets card and the visible event marker, populate per-window timing — so the day-layout cards (built in Plans A/B) display properly when the flag is flipped.

**Architecture:** Backend: thread the client's local datetime into `build_today_view` → `day_layout` (fixes the 2-hour activity-type resolver's UTC skew); attach Keep-Going oz/packets labels in `day_layout`; emit Keep-Going + event as visible non-tappable nudges and populate per-window open/close times in `cards_to_template_windows`/`build_today_view`. Mobile: send the client datetime, and render the event marker and Keep-Going nudge rows in `DayTimeline`. Per the product decision (1A) new cards show the SAME gram chips existing cards already show — no gram-visibility change. Role-gating is OUT of scope (separate task, decision 2A). `DAY_LAYOUT_V2` stays OFF — the user flips it after QA.

**Tech Stack:** Backend: Python 3.12 / FastAPI / SQLite / pytest. Mobile: React Native / Expo SDK 54 (never `npx expo`) / TypeScript / jest + ts-jest. Backend repo root: `/Users/mayurkhera/AthFuelPath`. Mobile repo root: `/Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile`.

---

## Decisions baked into this plan (from the user)
- **1A — grams:** new day-layout cards show the same `Xg carbs / Yg protein` chips the existing Today cards already show. No gram-visibility change in Plan C.
- **2A — role-gating:** NOT in Plan C. Parent-only server-side gating of macro/ratio fields is a separate security task. `DAY_LAYOUT_V2` stays OFF; user flips it after their own QA.

## Background facts (verified — read before starting)

**Backend flag path (Plan A, `build_today_view` in `api/services/today_service.py`):**
- When `day_layout_v2_enabled()` (env `DAY_LAYOUT_V2`=="true"): `_layout = build_day_layout(events, athlete, now=datetime.now())`; `template_windows = cards_to_template_windows(_layout["cards"])`. **`datetime.now()` is server-local** — the timezone bug. `build_day_layout(events, athlete, now)` already takes `now`; `resolve_activity_type(event, now)` compares it to event start (athlete-local) → UTC skew.
- `cards_to_template_windows(cards)` (in `api/services/day_layout.py`) currently sets `open_dt=None`, `close_dt=None`, `macro_focus` from `_CARD_TO_MACRO_FOCUS`, `is_nudge_only=bool(c["is_event"])`, category via `_CARD_TO_CATEGORY` (keep_going→"quick_snack").
- `build_today_view` loop splits `template_windows` into `tappable` (gets `assign_window_status`, gram chips via `_FOCUS_MACRO_PCT`) and `nudges`. The nudge branch (inside `if tw.get("is_nudge_only"):`) currently emits: `category=="between_games"` → a nudge; `category=="event"` → a nudge with `window_type="event"`/`status="event"`; everything else is skipped (invisible).
- `windows = sorted(tappable + nudges, key=sort_time)`. `assign_window_status` sets status done/next/upcoming on tappable only (by `logged`); it does NOT set `window_type`.

**`/today` route** (`api/routes/today.py:109`): `get_today_view(athlete_id, date=Query(None), v2=False)` → `build_today_view(athlete_id, conn, today=date, force_v2=v2)`.

**Keep-Going oz/packets source:** `window_distribution.keep_going_window(wt_kg, duration_min)` returns `{"athlete_label": "Grab a sports drink (N oz) or M applesauce/honey packet(s)...", "extra_hyd_oz": int, "cho_g": int, ...}` or `None` for ≤75 min. day_layout already emits a `keep_going` card (with `duration_min`) for >75-min events (standard + tournament). build_day_layout has `athlete["weight_lbs"]`.

**Mobile timing gate** (`components/today/WindowConfirmButton.tsx` `windowTiming`): `if (open && nowHHMM < open) return "future"` (locks with "🔒 opens at"); `if (close && nowHHMM > close) return "past"` (still tappable); empty open/close → `"current"` (tappable). So **missing open/close is safe** — populating them just restores the pre-open lock.

**Mobile Today render** (`components/today/DayTimeline.tsx`): iterates `windows`; `isNudge = w.status === "nudge"` → renders a non-tappable nudge row (dot + label + meta, "QUICK" tag); else renders a tappable row with the `WindowConfirmButton`. Gram chips (`{w.carbs_g}g carbs` / `{w.protein_g}g protein`) render for any window with those values. `TodayWindow` (in `hooks/useTodayView.ts`) has `status: "done"|"next"|"upcoming"|"nudge"` and `window_type`.

**Mobile today fetch** (`hooks/useTodayView.ts`): `getLocalDateStr()` → `GET /api/athletes/:id/today?date=<localDate>`.

**Test conventions:** Backend `python3 -m pytest tests/test_x.py -v` from `/Users/mayurkhera/AthFuelPath`; functions needing "now" take it as a param (never call `datetime.now()` inside pure logic). Mobile `npx jest <path>` + `npx tsc --noEmit 2>&1 | grep -v node_modules` from the mobile root. KNOWN pre-existing failures to ignore: backend `test_today_service.py::test_mission_items_iron_critical_for_girls` + the dirty-tree suites; mobile `coachThreadStore.test.ts` + `onboardingWizardV2.{events,athletes}Parity.test.tsx`.

---

## File Structure
- **Modify** `api/routes/today.py` — `get_today_view` accepts a `now` query param (client local ISO datetime) and passes it to `build_today_view`.
- **Modify** `api/services/today_service.py` — `build_today_view(..., now=None)`: use client `now` for the day_layout call (fallback server now); pass `today_str` to the adapter; emit `keep_going` nudges in the nudge branch.
- **Modify** `api/services/day_layout.py` — attach Keep-Going oz/packets `athlete_label` to keep_going cards; `cards_to_template_windows(cards, date_str)` maps keep_going → nudge-only with category `"keep_going"` + the label, and populates `open_dt`/`close_dt` from `sort_time`+date.
- **Modify** `hooks/useTodayView.ts` (mobile) — send `&now=<local ISO datetime>`; add `window_type "event"|"keep_going"` to the TodayWindow union if needed.
- **Modify** `components/today/DayTimeline.tsx` (mobile) — render the event marker (`status==="event"`) and Keep-Going (`status==="nudge"` with `window_type==="keep_going"`) rows.
- **Tests:** backend `tests/test_day_layout_today_integration.py` (extend); mobile `__tests__/components/dayTimeline.render.test.tsx` (new) or extend existing.

---

## Task C1: Thread client-local `now` into the 2-hour resolver (backend)

**Files:**
- Modify: `api/routes/today.py`
- Modify: `api/services/today_service.py`
- Test: `tests/test_day_layout_today_integration.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_day_layout_today_integration.py`:

```python
def test_build_today_view_uses_client_now_for_2h_resolver(monkeypatch):
    """An untagged event resolves via the CLIENT now, not the server clock."""
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    import sqlite3
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    from db.setup import init_db
    from api.services.db_migrations import run_all

    conn = get_conn(); init_db(); run_all()
    conn.execute("INSERT INTO parents (full_name, email, consent_confirmed) VALUES ('P','c1@x.com',1)")
    pid = conn.execute("SELECT id FROM parents WHERE email='c1@x.com'").fetchone()[0]
    conn.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
                 "VALUES (?, 'A', 14, 'boy', 120, 5, 4)", (pid,))
    aid = conn.execute("SELECT id FROM athletes WHERE parent_id=?", (pid,)).fetchone()[0]
    # Untagged event at 15:00; no activity_type. With client now = 11:00 (4h before),
    # >2h out → still untagged → day_layout treats as no resolved type → rest/standard.
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
                 "VALUES (?, 'Practice', 'practice', '2026-06-27', '15:00', 1.0)", (aid,))
    conn.commit()

    # Client now well before the 2h window — resolver returns None (untagged).
    early = build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 11, 0))
    # Client now within 2h — resolver defaults to practice → a standard event layout.
    late = build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 13, 30))
    conn.close()
    # The two now-values must be able to produce different day shapes (proves now is used).
    assert early is not None and late is not None
    early_keys = {w["slot_name"] for w in early["windows"]}
    late_keys = {w["slot_name"] for w in late["windows"]}
    assert early_keys != late_keys or early["day_type"] != late["day_type"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py::test_build_today_view_uses_client_now_for_2h_resolver -v`
Expected: FAIL — `build_today_view() got an unexpected keyword argument 'now'`.

- [ ] **Step 3: Implement the `now` parameter**

In `api/services/today_service.py`, change the `build_today_view` signature to accept `now`:
```python
def build_today_view(athlete_id: int, conn, today: str | None = None, force_v2: bool = False, now=None) -> dict | None:
```
In the flag branch (the `if day_layout_v2_enabled():` block), replace `now=datetime.now()` with the client-supplied `now` (fallback to server now):
```python
    if day_layout_v2_enabled():
        from datetime import datetime as _dt
        effective_now = now if now is not None else _dt.now()
        _layout = build_day_layout(events, athlete, now=effective_now)
        event_type       = _layout["day_type"]
        template_windows = cards_to_template_windows(_layout["cards"])
    else:
        ...
```
(Keep the existing timezone-limitation comment but update it to note `now` is now threaded from the route.)

In `api/routes/today.py`, update `get_today_view`:
```python
@router.get("/{athlete_id}/today")
def get_today_view(athlete_id: int, date: str = Query(None), v2: bool = False, now: str = Query(None)):
    conn = get_conn()
    try:
        from datetime import datetime as _dt
        client_now = None
        if now:
            try:
                client_now = _dt.fromisoformat(now)
            except ValueError:
                client_now = None
        data = build_today_view(athlete_id, conn, today=date, force_v2=v2, now=client_now)
        ...
```
(Adapt to the real handler body — keep the existing 404/return logic; only add the `now` param + parse + pass-through.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py -v`
Expected: PASS (existing + new). Also confirm flag-OFF unaffected: `python3 -m pytest tests/test_today_service.py -q` — only the known pre-existing failure remains.

- [ ] **Step 5: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath
git add api/routes/today.py api/services/today_service.py tests/test_day_layout_today_integration.py
git commit -m "feat: thread client-local now into day_layout 2h resolver (timezone fix)"
```

---

## Task C2: Keep-Going oz/packets card + event marker as nudges (backend)

**Files:**
- Modify: `api/services/day_layout.py`
- Modify: `api/services/today_service.py`
- Test: `tests/test_day_layout_today_integration.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_day_layout_today_integration.py`:

```python
def test_keep_going_renders_as_oz_packets_nudge():
    from api.services.day_layout import build_day_layout, cards_to_template_windows
    from datetime import datetime
    ev = {"id": 1, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.5}  # 90 min → keep_going
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    kg = next(c for c in res["cards"] if c["card"] == "keep_going")
    # day_layout attaches an athlete-facing oz/packets label (never grams)
    assert kg.get("athlete_label") and "oz" in kg["athlete_label"].lower()

    tw = cards_to_template_windows(res["cards"], "2026-06-27")
    kg_win = next(w for w in tw if w["category"] == "keep_going")
    assert kg_win["is_nudge_only"] is True            # non-tappable
    assert "oz" in kg_win["macro_focus"].lower()       # the label rides macro_focus
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py::test_keep_going_renders_as_oz_packets_nudge -v`
Expected: FAIL — keep_going card has no `athlete_label` / category isn't "keep_going".

- [ ] **Step 3: Implement — attach the oz/packets label in `build_day_layout`**

In `api/services/day_layout.py`, add the import:
```python
from api.services.window_distribution import keep_going_window
```
At the END of `build_day_layout`, after the day_type/cards are decided but before the final `return`, post-process keep_going cards to attach the athlete-facing label. The cleanest place: wrap the return so every path's cards get the label. Add a helper and apply it in each return. Add this helper near `_apply_guardrails`:
```python
def _attach_keep_going_labels(cards: list, wt_kg: float) -> list:
    """Attach the athlete-facing oz/packets label to keep_going cards (never grams)."""
    for c in cards:
        if c["card"] == "keep_going" and c.get("duration_min"):
            kg = keep_going_window(wt_kg, c["duration_min"])
            if kg:
                c["athlete_label"] = kg["athlete_label"]
    return cards
```
Compute `wt_kg` once at the top of `build_day_layout` (after resolving):
```python
    wt_kg_for_labels = athlete["weight_lbs"] * 0.453592 if athlete.get("weight_lbs") else 0
```
And wrap each `_apply_guardrails(...)` result with `_attach_keep_going_labels(..., wt_kg_for_labels)`. For the tournament return (which already computes `wt_kg`), reuse that. Example for the standard return:
```python
    return {"day_type": "standard",
            "cards": _attach_keep_going_labels(_apply_guardrails(cards), wt_kg_for_labels)}
```
(Apply the same wrap to the rest, active_recovery, and tournament returns. rest/active_recovery have no keep_going cards so the helper is a no-op there but keeps the code uniform.)

- [ ] **Step 4: Implement — adapter maps keep_going to a nudge with the label**

In `cards_to_template_windows`, change its signature to take the date and handle keep_going:
```python
def cards_to_template_windows(cards: list, date_str: str | None = None) -> list:
```
Change the keep_going mapping in `_CARD_TO_CATEGORY` from `"quick_snack"` to `"keep_going"`:
```python
    "keep_going": "keep_going", "event": "event",
```
In the loop, set `is_nudge_only` True for keep_going (in addition to event markers), and route the oz/packets label into `macro_focus` for keep_going:
```python
    for c in cards:
        category = _CARD_TO_CATEGORY.get(c["card"], "everyday")
        is_nudge = bool(c["is_event"]) or c["card"] == "keep_going"
        macro_focus = (c.get("athlete_label") or "") if c["card"] == "keep_going" \
                      else _CARD_TO_MACRO_FOCUS.get(c["card"], "")
        out.append({
            "key": c["key"], "label": c["label"],
            "category": category, "category_key": category,
            "macro_focus": macro_focus,
            "sort_time": c["sort_time"], "time_display": c.get("time_display", ""),
            "open_dt": None, "close_dt": None,   # populated in Task C3
            "is_nudge_only": is_nudge,
        })
    return out
```

- [ ] **Step 5: Implement — emit keep_going in the `build_today_view` nudge branch**

In `api/services/today_service.py`, inside `build_today_view`'s nudge branch (`if tw.get("is_nudge_only"):`), add a `keep_going` case alongside the existing `between_games` and `event` cases:
```python
            elif tw.get("category") == "keep_going":
                nudges.append({
                    "id":            None,
                    "slot_name":     sn,
                    "display_label": tw["label"],
                    "eat_by_time":   tw.get("time_display", ""),
                    "open_time":     "",
                    "close_time":    "",
                    "macro_focus":   tw.get("macro_focus", ""),   # the oz/packets label
                    "logged":        False,
                    "window_type":   "keep_going",
                    "sort_time":     sort_t,
                    "status":        "nudge",
                    "log":           {"logged": False, "method": None,
                                      "photo_thumb_url": None, "nutrient_status": "none"},
                })
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py tests/test_day_layout.py -v`
Expected: all pass (the new keep_going test + existing day_layout tests still green — note `cards_to_template_windows` now takes an optional `date_str`, default None, so existing single-arg callers in tests still work).

- [ ] **Step 7: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath
git add api/services/day_layout.py api/services/today_service.py tests/test_day_layout_today_integration.py
git commit -m "feat: Keep-Going renders as oz/packets nudge (never grams); event marker stays nudge"
```

---

## Task C3: Populate per-window open/close times (backend)

**Files:**
- Modify: `api/services/day_layout.py`
- Modify: `api/services/today_service.py`
- Test: `tests/test_day_layout_today_integration.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_day_layout_today_integration.py`:

```python
def test_cards_to_template_windows_populates_open_close_from_date():
    from api.services.day_layout import build_day_layout, cards_to_template_windows
    from datetime import datetime
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    tw = cards_to_template_windows(res["cards"], "2026-06-27")
    fb = next(w for w in tw if w["key"] == "fuel_before")
    assert fb["open_dt"] is not None and fb["close_dt"] is not None
    assert fb["open_dt"].strftime("%H:%M") == fb["sort_time"]   # open == sort_time
    assert fb["close_dt"] > fb["open_dt"]                        # close after open

def test_cards_to_template_windows_open_close_none_without_date():
    from api.services.day_layout import build_day_layout, cards_to_template_windows
    from datetime import datetime
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    tw = cards_to_template_windows(res["cards"])   # no date_str → open/close stay None
    assert all(w["open_dt"] is None for w in tw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py::test_cards_to_template_windows_populates_open_close_from_date -v`
Expected: FAIL — open_dt is None even when date_str given.

- [ ] **Step 3: Implement open/close population**

In `cards_to_template_windows` (api/services/day_layout.py), when `date_str` is provided, build `open_dt` from `date_str`+`sort_time` and `close_dt = open_dt + 60 min`. Add at the top of the function:
```python
    from datetime import datetime, timedelta
    def _to_dt(hhmm: str):
        if not date_str or not hhmm:
            return None
        return datetime.strptime(f"{date_str} {hhmm}", "%Y-%m-%d %H:%M")
```
In the loop, replace the `"open_dt": None, "close_dt": None,` line with:
```python
            "open_dt":  _to_dt(c["sort_time"]),
            "close_dt": (_to_dt(c["sort_time"]) + timedelta(minutes=60)) if (date_str and c["sort_time"]) else None,
```

- [ ] **Step 4: Pass `today_str` from `build_today_view` into the adapter**

In `api/services/today_service.py`, the flag branch calls `cards_to_template_windows(_layout["cards"])`. Change it to pass the date:
```python
        template_windows = cards_to_template_windows(_layout["cards"], today_str)
```
(`today_str` is already computed at the top of `build_today_view`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout_today_integration.py tests/test_day_layout.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath
git add api/services/day_layout.py api/services/today_service.py tests/test_day_layout_today_integration.py
git commit -m "feat: populate day_layout window open/close times from event date"
```

---

## Task C4: Mobile sends client-local datetime (mobile)

**Files:**
- Modify: `hooks/useTodayView.ts`
- Test: `__tests__/components/todayNow.test.ts` (new — pure helper)

- [ ] **Step 1: Write the failing test**

Create `__tests__/components/todayNow.test.ts`:

```ts
import { getLocalDateTimeStr } from "../../hooks/useTodayView";

describe("getLocalDateTimeStr", () => {
  it("returns a local 'YYYY-MM-DDTHH:MM' string (no timezone Z suffix)", () => {
    const s = getLocalDateTimeStr(new Date(2026, 5, 27, 13, 5)); // month is 0-based → June
    expect(s).toBe("2026-06-27T13:05");
    expect(s.endsWith("Z")).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/todayNow.test.ts`
Expected: FAIL — `getLocalDateTimeStr` is not exported.

- [ ] **Step 3: Implement**

In `hooks/useTodayView.ts`, add a local-datetime helper next to `getLocalDateStr` and export it:
```ts
function getLocalDateTimeStr(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day}T${hh}:${mm}`;
}
```
Add it to the exports at the bottom: `export { getLocalDateStr, getLocalDateTimeStr };`
In `useTodayView`, include `now` in the request and the query key:
```ts
export function useTodayView() {
  const athleteId = useAuthStore((s) => s.selectedAthleteId);
  const localDate = getLocalDateStr();
  const localNow = getLocalDateTimeStr();

  return useQuery<TodayView>({
    queryKey: ["today-view", athleteId, localDate],
    queryFn: () => api.get(`/api/athletes/${athleteId}/today?date=${localDate}&now=${encodeURIComponent(localNow)}`),
    enabled: !!athleteId,
    staleTime: 2 * 60 * 1000,
  });
}
```
(Keep the queryKey on `localDate` only — NOT `localNow` — so the query doesn't refetch every minute; `now` only affects the untagged-event 2h default, which is acceptable to resolve on the date-keyed fetch / manual refresh.)

- [ ] **Step 4: Run test + typecheck**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/todayNow.test.ts` → PASS.
Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx tsc --noEmit 2>&1 | grep useTodayView` → no output.

- [ ] **Step 5: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
git add hooks/useTodayView.ts __tests__/components/todayNow.test.ts
git commit -m "feat(mobile): send client-local datetime to /today (now param)"
```

---

## Task C5: Render the event marker + Keep-Going nudge (mobile)

**Files:**
- Modify: `hooks/useTodayView.ts` (TodayWindow union)
- Modify: `components/today/DayTimeline.tsx`
- Test: `__tests__/components/dayTimeline.render.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

Create `__tests__/components/dayTimeline.render.test.tsx`:

```tsx
import React from "react";
import { render } from "@testing-library/react-native";
import { DayTimeline } from "../../components/today/DayTimeline";
import type { TodayWindow } from "../../hooks/useTodayView";

function win(partial: Partial<TodayWindow>): TodayWindow {
  return {
    id: null, slot_name: "x", display_label: "X", eat_by_time: "3:00 PM",
    open_time: "", close_time: "", macro_focus: "", logged: false,
    window_type: null, status: "upcoming", carbs_g: null, protein_g: null,
    log: { logged: false, method: null, photo_thumb_url: null, nutrient_status: "none" },
    ...partial,
  };
}

describe("DayTimeline new card kinds", () => {
  it("renders an event marker (status 'event') as a non-tappable row, no confirm button", () => {
    const ev = win({ slot_name: "event_g1", display_label: "Game 1", status: "event" as any, window_type: "event" as any });
    const { getByText, queryByText } = render(
      <DayTimeline windows={[ev]} dayType="standard" onConfirm={() => {}} onUnconfirm={() => {}} />,
    );
    getByText("Game 1");
    // no confirm affordance for the event marker
    expect(queryByText("Yes")).toBeNull();
  });

  it("renders a Keep-Going nudge showing the oz/packets label", () => {
    const kg = win({
      slot_name: "keep_going", display_label: "Keep Going", status: "nudge",
      window_type: "keep_going" as any,
      macro_focus: "Grab a sports drink (20 oz) or 1 applesauce/honey packet(s).",
    });
    const { getByText } = render(
      <DayTimeline windows={[kg]} dayType="standard" onConfirm={() => {}} onUnconfirm={() => {}} />,
    );
    getByText(/sports drink/i);
  });
});
```

NOTE: if `@testing-library/react-native` is not installed, mirror the project's existing render-test approach (react-test-renderer + the shared `__tests__/__mocks__/reactNative.js`, as `activityTypeSheet.render.test.tsx` does). Adapt the assertions to find the rendered text nodes accordingly.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/dayTimeline.render.test.tsx`
Expected: FAIL — the event marker currently renders a confirm button (status "event" falls through to the tappable branch).

- [ ] **Step 3: Widen the TodayWindow union**

In `hooks/useTodayView.ts`, extend the `TodayWindow` `status` and `window_type` unions to include the new values:
```ts
  window_type: "pre_fuel" | "recovery" | "nudge" | "event" | "keep_going" | null;
  status: "done" | "next" | "upcoming" | "nudge" | "event";
```

- [ ] **Step 4: Render the event marker in DayTimeline**

In `components/today/DayTimeline.tsx`, inside the `windows.map(...)`, add an event-marker branch BEFORE the existing `if (isNudge)` block. Compute `const isEvent = w.status === "event";` near the other status flags, then:
```tsx
        if (isEvent) {
          return (
            <View key={w.slot_name} style={styles.row}>
              <View style={styles.spineCol}>
                <View style={styles.dotEvent} />
                {!isLast && <View style={styles.line} />}
              </View>
              <View style={[styles.content, !isLast && styles.contentPad]}>
                <View style={styles.labelRow}>
                  <Text style={styles.labelEvent}>⚽ {w.display_label}</Text>
                  <View style={styles.tagArea}>
                    <View style={styles.tagEvent}><Text style={styles.tagTextEvent}>EVENT</Text></View>
                  </View>
                </View>
                {w.eat_by_time ? <Text style={styles.meta}>{w.eat_by_time}</Text> : null}
              </View>
            </View>
          );
        }
```
Add the styles to the `StyleSheet.create`:
```tsx
  dotEvent:     { width: 22, height: 22, borderRadius: 11, backgroundColor: DS.secondary },
  labelEvent:   { fontSize: 14, fontWeight: "700", color: DS.secondary, flex: 1 },
  tagEvent:     { backgroundColor: DS.secondary + "18", paddingHorizontal: 7, paddingVertical: 2, borderRadius: 4 },
  tagTextEvent: { fontSize: 10, fontWeight: "700", color: DS.secondary },
```
The Keep-Going nudge already renders via the existing `isNudge` branch (status "nudge"): its `display_label` ("Keep Going") and `macro_focus` (the oz/packets label) show in that row. No change needed for keep_going beyond confirming the label text appears — the second test verifies it. (If the oz/packets label is long, the existing `metaRow` wraps; acceptable.)

- [ ] **Step 5: Run test + typecheck**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/dayTimeline.render.test.tsx` → PASS.
Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx tsc --noEmit 2>&1 | grep -E "DayTimeline|useTodayView"` → no output.

- [ ] **Step 6: Commit**

```bash
cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile
git add hooks/useTodayView.ts components/today/DayTimeline.tsx __tests__/components/dayTimeline.render.test.tsx
git commit -m "feat(mobile): render event marker + Keep-Going oz/packets nudge in DayTimeline"
```

---

## Task C6: Final verification (backend + mobile)

**Files:** none (verification only)

- [ ] **Step 1: Backend — day-layout + today suites**

Run: `cd /Users/mayurkhera/AthFuelPath && python3 -m pytest tests/test_day_layout.py tests/test_day_layout_today_integration.py tests/test_today_service.py -q`
Expected: all pass except the known pre-existing `test_mission_items_iron_critical_for_girls`. No NEW failures.

- [ ] **Step 2: Mobile — Plan C tests + typecheck**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest __tests__/components/todayNow.test.ts __tests__/components/dayTimeline.render.test.tsx` → all pass.
Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx tsc --noEmit 2>&1 | grep -v node_modules` → no NEW errors from Plan C files.

- [ ] **Step 3: Mobile — full suite, confirm no new regressions**

Run: `cd /Users/mayurkhera/AthFuelPath_Mobile/fuelup-mobile && npx jest 2>&1 | tail -6`
Expected: the only failures are the known pre-existing 3 suites (coachThreadStore + 2 onboardingWizardV2). No new failures.

- [ ] **Step 4: No commit** (verification only). Fix under the relevant task if anything surfaces.

---

## After all tasks

- [ ] Use **superpowers:finishing-a-development-branch**.
- [ ] **Hand-off to the user — enabling the feature:** `DAY_LAYOUT_V2` is still OFF. To QA: set `DAY_LAYOUT_V2=true` (Fly secret / env) and open an athlete's Today tab with a tagged event. Verify: morning/afternoon card order, the visible event marker, Keep-Going oz/packets on a >75-min session, tournament multi-game ordering, evening wind-down. The user runs the flip + any TestFlight build.
- [ ] **Still deferred (separate tasks, NOT Plan C):** server-side parent-only role-gating of macro/ratio fields (decision 2A); the §14.3 grams-to-athletes philosophy question (decision 1A kept current behavior — Purvi to revisit); the 33/34/33 rest-day gram split (downstream gram concern).

---

## Self-Review

**Spec coverage:**
- Timezone before-enabling item → Task C1 ✅
- Keep-Going oz/packets (never grams) rendering → Task C2 (backend label + nudge) + Task C5 (mobile shows label) ✅
- Visible event marker (decision 3b) → Task C2 (backend nudge, window_type "event") + Task C5 (DayTimeline event branch) ✅
- Per-window timing/status before-enabling item → Task C3 (open/close) + existing `assign_window_status` (status) ✅
- New cards show grams matching current (decision 1A) → no change needed; the existing DayTimeline gram chips render for tappable day-layout cards (recharge/rebuild/everyday/wind_down) automatically ✅
- Flag stays OFF, user flips after QA (decision 2A) → After-all-tasks hand-off ✅

**Gaps flagged, not dropped:** role-gating + the §14.3 grams philosophy + 33/34/33 rest split are explicitly deferred (After-all-tasks). The Keep-Going label is carried on `macro_focus` (reusing the existing nudge display field) rather than a new field — a deliberate minimal-surface choice, documented in Task C2.

**Placeholder scan:** every code step has complete code; every test step has real assertions; the mobile render-test step explicitly handles the "if @testing-library not installed, use react-test-renderer" fork (matching the repo's existing pattern, as discovered in Plan B).

**Type consistency:** `cards_to_template_windows(cards, date_str=None)` signature consistent across C2 (adds keep_going) and C3 (adds open/close) and the C2/C3 build_today_view call sites. `now` param consistent across C1 route → build_today_view → build_day_layout. `window_type "event"|"keep_going"` and `status "event"` added to the TodayWindow union (C5) match what the backend emits (C2). `getLocalDateTimeStr` consistent between C4 definition/export and its test.
