# ADR: Protein calculation stays event-derived (soccer-only) — no `sport_type`, no migration

**Status:** Accepted — **RDN-signed-off 2026-06-24** (both clinical items resolved; see Resolution)
**Date:** 2026-06-24
**Scope:** `api/services/nutrition_calc.py` protein + hydration paths. Documentation only — no logic changed.

## Decision

AthFuelPath is a **soccer-only** app today. The current protein calculation is already correct for that population, so we are making **no code change**:

- **No `sport_type` profile field.**
- **No DB migration.**
- **No engine change** to `nutrition_calc.py`, `fueling_targets.py`, or `fuel_gauge.py`.
- **No edits to any factor table** (no adding `other`/`tennis`/`cycling`, no codifying the `.get(..., 1.6)` default).

This ADR exists so the "zero changes" outcome is **recorded as a deliberate decision**, not mistaken for an oversight or an unfinished migration later.

## Evidence (from live source)

- Protein factors already hold the correct values — `SPORT_PROT` (`api/services/nutrition_calc.py:73-76`):
  ```
  SPORT_PROT  = {
      "soccer": 1.6, "basketball": 1.6, "volleyball": 1.6,
      "running": 1.4, "swimming": 1.4, "strength": 1.8,
  }
  ```
  → `soccer = 1.6`, `strength = 1.8`.
- Sport is **derived from the event**, not from a profile field — `_sport_type_from_event` (`api/services/nutrition_calc.py:156-159`) returns `"strength"` only for strength events and `"soccer"` for every other event type.
- The protein line resolves through that helper — `api/services/nutrition_calc.py:193-195`:
  ```
  sport_type = _sport_type_from_event(norm)
  prot_fac = SPORT_PROT.get(sport_type, 1.6)
  protein_g = round(wt_kg * prot_fac * SEASON_PROT.get(season, 1.0), 1)
  ```
- Net effect for a soccer-only population: every match / practice / training / tournament / rest event → **1.6**; a logged strength/conditioning session → **1.8**. No other sport factor is reachable, so the absence of a `sport_type` field changes no output.

## Resolution — RDN (Purvi) sign-off, 2026-06-24

Both clinical items below were ruled on by Purvi. **Both rulings confirm the current code**, so no code change resulted — the engine already implements both decisions.

**(a) Hydration constants — RULING: KEEP 109 oz.** The app keeps the live `+27` / `+36` oz formula (`api/services/nutrition_calc.py:200`), yielding **≈109 oz/day for the 46 kg reference athlete**. This is a **deliberate, signed-off deviation** from the dietician spec's `500 mL` (pre) + `1000 mL` (meals) values (~97 oz/day, ~12 oz lower). Purvi confirmed **109 oz is intended**; the spec's mL constants are not adopted. No change to `nutrition_calc.py:200`.

**(b) Strength-day protein — RULING: 1.8 g/kg.** A soccer athlete who logs a **strength** session receives a **1.8** protein factor, not 1.6. The dietician spec was internally contradictory (factor table `strength = 1.8` vs the Phase 3 "protein is flat every day" narrative). Purvi ruled in favor of **1.8 on lifting days**, matching the factor table and today's code (`SPORT_PROT["strength"] = 1.8`, `nutrition_calc.py:75`). No change to the table or the protein line.

With both items signed off, the protein/hydration engine is **clinically validated** as-is. No PENDING status remains.

## Deferred (not rejected)

The **nullable `sport_type` profile field + event-derived fallback** design (athletes who set a sport use it; everyone else keeps event-derived behavior) is **deferred, not rejected**. Revisit only **if/when a second sport is added** to the app. At that point the gate items from the earlier audit must be reconciled with Purvi first: the dietician table adds `tennis`/`cycling`/`other` keys not present in live `SPORT_PROT`, and the accepted-value set did not include `volleyball` (which *is* a live key). None of that is needed while the app is soccer-only.

## Consequences

- No regression risk: nothing executed changed.
- Future readers see two inline comments (`nutrition_calc.py` near `:193` and `:200`) pointing back to this ADR so working code is not "fixed" by mistake.
- Purvi ruled on both (a) and (b) on 2026-06-24; both confirmed current code, so the PENDING CLINICAL VALIDATION status is lifted with zero code change.
