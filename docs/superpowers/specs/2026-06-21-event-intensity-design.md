# Event Intensity — Design Spec

**Date:** 2026-06-21
**Status:** Approved
**Author:** Principal-engineer design pass (AthFuelPath)

---

## 1. Problem

Nutrition targets are currently driven **only** by `event_type` (`nutrition_calc.py`). Two soccer "games" of identical type produce identical carb/protein targets — a low-key league match and a high-stakes tournament final are nutritionally indistinguishable. We need to capture the **intensity** of each event so recommendations (and the dietician) can scale carbohydrate and protein within the science-backed ranges.

Intensity must be captured for **both** event entry paths:
- **Manual add/edit** — a parent is present and can tell us directly.
- **ICS bulk import** — events are auto-parsed from a calendar; there is no per-event human step.

## 2. Goals & Non-Goals

**Goals**
- Capture a per-event intensity (`low` / `medium` / `high`) and persist it.
- Use intensity to reposition **carbohydrate and protein** targets *within* the existing Everett/ACSM g/kg ranges — never outside them.
- Make the captured value visible to the dietician/AI per event and per date.
- Require an explicit parent choice for manual events; derive silently for imported/legacy events.

**Non-Goals (MVP)**
- Intensity-scaling of calories/PAL, hydration, or micronutrients (kept event-type-driven; clean future extension).
- Per-event intensity override UI beyond the standard add/edit form.
- Showing intensity to the youth athlete (it is a parent-facing schedule input only).

## 3. Decisions (locked)

| # | Decision | Choice |
|---|---|---|
| 1 | Scale | 3-level: `low` / `medium` / `high` (stored lowercase) |
| 2 | Calc effect | Reposition **carbs + protein** within the scientific g/kg band (Low → lower half, Medium → middle 50%, High → upper half). `None` → full band (unchanged). |
| 3 | Manual capture | **Blank, required** dropdown in Add/Edit Event — no pre-fill; parent must choose |
| 4 | ICS capture | Silent — backend derives `derive_intensity(event_type, competition_level)` |
| 5 | Legacy rows | Backfilled via the same derivation |
| 6 | Competition Level | Consolidated to 3 tiers with examples (frontend) |
| 7 | Null competition level | `low` |

## 4. Derivation rule (ICS + backfill + any missing value)

Manual events always carry an explicit intensity, so derivation only fills the automated/legacy gap.

```
derive_intensity(event_type, competition_level) -> "low" | "medium" | "high":
    if normalize_event_type(event_type) == "rest":     # yoga / flexibility / recovery / off / rest
        return "low"                                    # intrinsically low for EVERYONE
    level = (competition_level or "").strip().lower()
    if level == "":               return "low"          # null default
    if "elite"        in level:   return "high"
    if "recreational" in level:   return "low"
    if "competitive" in level or "club" in level: return "medium"
    return "low"                                         # unknown -> low
```

Substring matching means the rule absorbs **both** the new 3 labels and the legacy 4-value data already in the DB — **no `competition_level` data migration is required**:

| Stored `competition_level` (new + legacy) | Intensity |
|---|---|
| `Elite Club`, legacy `Elite` | high |
| `Recreational` | low |
| `Competitive Club`, legacy `Club`, legacy `Competitive` | medium |
| empty / null / unrecognized | low |

The `normalize_event_type` "rest" bucket already covers `yoga/flexibility/recovery`, `recovery`, `off`, `rest` (see `EVENT_TYPE_MAP`), so recovery-type events floor to `low` for everyone — including Elite Club athletes.

## 5. Capture paths

| Path | Source of intensity | UI |
|---|---|---|
| Manual add | Required dropdown, sent explicitly | Blank `Low/Medium/High`, cannot submit empty |
| Manual edit | Same dropdown, shows current value, editable | Also used to correct imported events |
| ICS import | Backend derives `derive_intensity(...)` | None |
| Legacy rows | Backend derives (migration backfill) | None |

**Consequence (intentional):** because manual events are always explicit, `competition_level` influences **only** imported and backfilled events. This is consistent and acceptable.

**API contract:** `intensity` is **optional** on `EventCreate` / `EventUpdate`. The "required" rule is a **frontend constraint on the manual form**, not an API-schema requirement (so the ICS path can omit it).
- **Create:** if provided → validate + store; if absent → derive `derive_intensity(event_type, competition_level)`.
- **Update:** if provided → validate + store; if absent → **keep the existing stored value** (do not clobber); if the existing value is null (legacy), derive.

## 6. Data model

Additive only (existing `db_migrations.py` `PRAGMA table_info → ALTER TABLE` pattern).

- `events.intensity TEXT` (nullable). Backfilled on migration from `derive_intensity(event.event_type, athlete.competition_level)`.
- `daily_targets.intensity TEXT` (nullable). Written when targets are computed, so each date's stored recommendation records which intensity drove it.

`intensity` is added to `EventResponse`.

## 7. Nutrition effect (`nutrition_calc.py`)

`calc_daily_targets(athlete, event_type, intensity=None)`:
- `intensity is None` → return the **full** g/kg band (today's behavior — keeps the blueprint, which computes generic per-event-type targets, unchanged).
- `intensity` given → reposition carbs + protein within the band before multiplying by body weight:

```
_reposition(lo, hi, intensity):
    span = hi - lo
    low    -> (lo,            lo + 0.5*span)     # lower half
    high   -> (lo + 0.5*span, hi)                # upper half
    medium -> (lo + 0.25*span, hi - 0.25*span)   # middle 50%
```

Applied to `CARB_TARGETS[norm]` and `PROTEIN_TARGETS[norm]` (g/kg) only; calories, fat, hydration, iron, calcium unchanged. Rounding stays as today (`int()` for carbs, `round(...,1)` for protein).

**Worked example** — 50 kg athlete, `game` (carb band 8–10 g/kg = 400–500 g):

| Intensity | g/kg band | Carbs (g) |
|---|---|---|
| Low | 8.0–9.0 | 400–450 |
| Medium | 8.5–9.5 | 425–475 |
| High | 9.0–10.0 | 450–500 |
| None (blueprint) | 8.0–10.0 | 400–500 |

**Threading intensity into the calc:**
- `nutrition.py /targets` route already resolves the day's event row → pass `event.intensity`. Also store `intensity` into `daily_targets`.
- `today.py` and `coach_service.py`: pass the resolved event's intensity when a specific event exists.
- `athletes.py` blueprint: passes **no** intensity (`None`) → full band, unchanged.

## 8. Frontend changes

**Competition Level → 3 tiers** (`Onboarding.jsx`, `ProfileScreen.jsx`):

| Stored value | Helper examples |
|---|---|
| Recreational | AYSO, YMCA, etc. |
| Competitive Club | Most travel clubs, NorCal, NPL lower division |
| Elite Club | ECNL, GA, MLS Next, DPL, EA, etc. |

**Add/Edit Event** (`ScheduleScreen.jsx`):
- New required `intensity` `<select>` (blank default + Low/Medium/High) alongside the activity-type select, in both add and edit forms.
- Submit disabled / inline error until a value is chosen.
- The save call sends `intensity`.
- **ICS import path sends no `intensity`** (backend derives). Event cards may show a small intensity badge (nice-to-have).

## 9. Future-ready hooks (built, not used in MVP)

- Per-event storage already supports a future per-event override flow.
- `derive_intensity` is the single swap-point if intensity later comes from a wearable training-load score instead of competition level.
- `daily_targets.intensity` gives the dietician an audit trail of what drove each date's numbers.

## 10. Testing

- `derive_intensity`: rest floor → low (incl. Elite); each new label; each legacy label; null → low; unknown → low.
- `_reposition` / `calc_daily_targets`: low/medium/high bands for a known weight+event; `intensity=None` returns the unchanged full band; repositioned values never exceed the science band.
- Migration: `events.intensity` and `daily_targets.intensity` columns created; existing events backfilled from competition level; idempotent re-run.
- Route: `POST /api/events` with explicit intensity stores it; without intensity derives it; `EventResponse` includes `intensity`.

## 11. Files touched

- `api/services/db_migrations.py` — `_add_intensity_to_events`, `_add_intensity_to_daily_targets` (+ backfill); wired into `run_all()`.
- `api/services/nutrition_calc.py` — `derive_intensity`, `_reposition`, `intensity` param on `calc_daily_targets`.
- `api/routes/events.py` — set intensity on create/update.
- `api/routes/nutrition.py` — thread event intensity into calc + store in `daily_targets`.
- `api/models.py` — optional `intensity` on `EventCreate`/`EventUpdate`, field on `EventResponse`.
- `frontend/src/Onboarding.jsx`, `frontend/src/ProfileScreen.jsx` — 3-tier competition level.
- `frontend/src/ScheduleScreen.jsx` — required intensity dropdown (add/edit), badge.
- `tests/` — unit tests as above.
- `docs/HLD.md` — document the field, derivation, and calc effect.
