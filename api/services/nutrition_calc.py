from datetime import date
from typing import Optional

from api.services.activity_engine import get_activity_profile
from api.services.activity_type_resolver import VALID_ACTIVITY_TYPES

EVENT_TYPE_MAP = {
    "soccer game": "game",
    "game": "game",
    "soccer tournament": "tournament",
    "tournament": "tournament",
    "club soccer practice": "practice",
    "practice": "practice",
    "private soccer training": "training",
    "training": "training",
    "speed/agility training": "training",
    "agility": "training",
    "strength/conditioning": "strength",
    "strength": "strength",
    "yoga/flexibility/recovery": "rest",
    "yoga": "rest",
    "recovery": "rest",
    "rest": "rest",
    "pre-game day": "practice",
    "post-game recovery day": "rest",
    # Two training/practice sessions, not a multi-game tournament — was
    # incorrectly bucketed as "tournament", inheriting its max carb tier.
    "double training day": "training",
}

# Lifestyle PAL — non-training daily activity level (onboarding field; default "light")
PAL = {
    "sedentary": 1.3,   # mostly sitting — school desk, homework, screens
    "light":     1.4,   # mix of sitting and moving (DEFAULT)
    "moderate":  1.5,   # on feet most of the day
}

# Maps nutrition_calc normalized event types → activity_engine activity types (Option A)
NORM_TO_ACTIVITY_TYPE = {
    "rest":       "active_recovery",
    "practice":   "practice",
    "training":   "practice",      # speed/agility also maps to practice (Option A)
    "strength":   "strength_cond",
    "game":       "game",
    "tournament": "tournament",
}

CARB_TARGETS = {  # g/kg
    "rest": (4, 5),
    "practice": (6, 8),
    "training": (6, 8),
    "strength": (6, 8),
    "game": (8, 10),
    "tournament": (10, 12),
}

PROTEIN_TARGETS = {  # g/kg
    "rest": (1.2, 1.4),
    "practice": (1.4, 1.6),
    "training": (1.4, 1.6),
    "strength": (1.8, 2.0),
    "game": (1.6, 1.8),
    "tournament": (1.8, 2.0),
}

HYDRATION_TARGETS = {  # oz/day — legacy fallback only
    "rest": (64, 72),
    "practice": (72, 80),
    "training": (72, 80),
    "strength": (72, 80),
    "game": (80, 88),
    "tournament": (88, 96),
}

# ── Spec-formula tables (getDashboardTargets) ─────────────────────────────────
# No dedicated "tournament" tier: a tournament day's carb target now comes from
# the same "hard" tier a demanding game day gets (8 g/kg). The event-type LABEL
# "tournament" used to force a flat 10 g/kg regardless of actual session length
# or measured intensity — a short single-game "tournament" got a full all-day
# carb prescription with no matching calorie budget to pay for it (Purvi,
# 2026-07-27 — root cause of the negative fat_g defect fixed separately).
CHO_FACTOR = {
    "rest":       {"any": 4.0},
    "low":        {"any": 4.0},
    "moderate":   {"lt60": 6.0, "bt6090": 6.0, "gt90": 6.0},
    "hard":       {"lt60": 8.0, "bt6090": 8.0, "gt90": 8.0},
}

SEASON_CHO  = {"in_season": 1.0, "off_season": 0.90, "post_season": 0.85}
SEASON_PROT = {"in_season": 1.0, "off_season": 1.05, "post_season": 0.95}

SPORT_PROT = {
    "soccer": 1.50, "basketball": 1.50, "volleyball": 1.50,
    "tennis": 1.50, "other": 1.50,
    "running": 1.50, "swimming": 1.50,
    "strength": 1.50,
}

# Flat 1.5 g/kg/day for all sports and day types (Purvi, July 2026).
SC_PROT_BUMP = 0.0

# +10 / +15 % for plant-based athletes (lower leucine bioavailability — ISSN Position Stand)
DIET_PROT_MULT = {
    "omnivore":   1.00,
    "vegetarian": 1.10,
    "vegan":      1.15,
}

# Energy Availability thresholds — IOC Mountjoy et al. 2023
EA_FLOOR   = {"female": 30, "male": 25}   # kcal/kg FFM — sex-specific RED/YELLOW boundary
EA_OPTIMAL = 45                             # kcal/kg FFM — GREEN threshold (all sexes)

_ENDURANCE_SPORTS = {"running", "cross_country", "swimming", "cycling"}
# Iron endurance set is a superset — gymnastics added for iron-depletion risk
# but NOT merged into _ENDURANCE_SPORTS (FFM% for gymnasts differs from runners/swimmers)
_IRON_ENDURANCE = _ENDURANCE_SPORTS | {"gymnastics"}

# Absolute calorie floor — conservative early-warning, below true clinical minimum.
# Flag is a signal, not a diagnosis. Parent dashboard only; never shown to athlete.
KCAL_FLOOR   = {"female": 1800, "male": 2000}
_HIGH_DEMAND = {"soccer", "basketball", "cross_country", "swimming", "running", "football"}

# Hydration — ACSM (2017), GSSI Desbrow 2020
SWEAT_RATE = {
    "soccer": 1.50, "lacrosse": 1.40, "basketball": 1.25, "running": 1.80,
    "cross_country": 1.80, "swimming": 0.50, "volleyball": 0.85, "tennis": 1.20,
    "football": 1.60, "wrestling": 1.30, "gymnastics": 0.70, "golf": 0.45,
    "baseball": 0.50, "diving": 0.40, "cycling": 1.40, "strength": 1.00, "other": 1.00,
}
HEAT_MULT        = 1.30   # outdoor + temp ≥ 80°F
HUMID_MULT       = 1.15   # humidity > 70%
COLD_MULT        = 0.85   # temp < 50°F
FEMALE_HYD_ADD_OZ = 8     # luteal phase baseline add — always-on (no cycle tracking yet); GSSI (2020)


def lbs_to_kg(lbs: float) -> float:
    return lbs * 0.453592


def ft_in_to_cm(ft: int, inches: float) -> float:
    return (ft * 12 + inches) * 2.54


def calc_age(dob_str=None, age_fallback=None):
    """
    Returns decimal age as float.
    Prefers dob_str (ISO format 'YYYY-MM-DD') when available.
    Falls back to age_fallback integer for existing athletes with no DOB.
    # MIGRATION BRIDGE — remove fallback path once DOB capture rate >95%
    """
    if dob_str:
        dob = date.fromisoformat(dob_str)
        today = date.today()
        return float(
            today.year - dob.year -
            ((today.month, today.day) < (dob.month, dob.day))
        )
    if age_fallback is not None:
        return float(age_fallback)  # MIGRATION BRIDGE
    raise ValueError("calc_age requires either dob_str or age_fallback")


def normalize_event_type(event_type: str) -> str:
    return EVENT_TYPE_MAP.get(event_type.lower().strip(), "rest")


def derive_intensity(event_type: str, competition_level: Optional[str]) -> str:
    """Derive intensity (low/medium/high) for ICS-imported, legacy, or
    otherwise-unspecified events. Manual events carry an explicit value.

    Rest/recovery events floor to "low" for everyone; all other events map
    from competition level. Tolerant of both the 3 current labels and the
    legacy 4-value labels."""
    if normalize_event_type(event_type) == "rest":
        return "low"
    level = (competition_level or "").strip().lower()
    if level == "":
        return "low"
    if "elite" in level:
        return "high"
    if "recreational" in level:
        return "low"
    if "competitive" in level or "club" in level:
        return "medium"
    return "low"


def _reposition(lo: float, hi: float, intensity: str):
    """Return a sub-band positioned within [lo, hi] by intensity.
    Never exceeds the original scientific bounds."""
    span = hi - lo
    if intensity == "low":
        return lo, lo + 0.5 * span
    if intensity == "high":
        return lo + 0.5 * span, hi
    # medium (and any unexpected value): middle 50%
    return lo + 0.25 * span, hi - 0.25 * span


def _to_activity_type(norm: str) -> str:
    return NORM_TO_ACTIVITY_TYPE.get(norm, "practice")


def calc_tdee(rmr: float, pal: float, activity_aee: float, phv_extra_kcal: float = 0) -> int:
    """TDEE = (RMR × lifestyle PAL) + Activity Energy Expenditure + PHV bonus.

    pal             — from PAL dict, keyed by athlete.lifestyle_activity.
    activity_aee    — from get_activity_profile() in activity_engine.py.
    phv_extra_kcal  — from check_growth_phase(); 0 outside PHV window.
    """
    return round(rmr * pal + activity_aee + phv_extra_kcal)


def _normalize_sex(gender: str) -> str:
    """Map app gender strings to binary 'female'/'male' for RMR formulas.
    'Prefer not to say' defaults to 'male' (higher RMR = avoids underestimating needs)."""
    g = gender.lower().strip()
    if g in ("girl", "female", "f"):
        return "female"
    return "male"


def calc_rmr(wt_kg: float, ht_cm: float, sex: str, age_yr: float) -> float:
    """Age-stratified RMR — dietician-approved (Purvi, 2026-06-26).

    13–19  Reale (2020) — validated for competitive youth athletes.
    <  13  Schofield (1985) — pediatric reference.
    >= 20  Mifflin-St Jeor — adult fallback (edge case only for this app).

    sex must be 'female' or 'male' (use _normalize_sex before calling).
    NEVER use Harris-Benedict for athletes under 18.
    """
    if 13 <= age_yr <= 19:
        return round(11.1 * wt_kg + 8.4 * ht_cm - (537 if sex == "female" else 340))
    if age_yr < 13:
        # Schofield (1985) pediatric
        if sex == "female":
            return round(16.97 * wt_kg + 1.618 * ht_cm + 371)
        return round(19.59 * wt_kg + 1.303 * ht_cm + 414)
    # Mifflin-St Jeor for age 20+
    base = 10 * wt_kg + 6.25 * ht_cm - 5 * age_yr
    return round(base - 161 if sex == "female" else base + 5)


def check_growth_phase(age_yr: float, sex: str) -> dict:
    """Peak Height Velocity window — calories and protein needs elevated.

    Female PHV: ~11–13 yrs.  Male PHV: ~13–15 yrs.
    Source: Domaradzki et al. (2022), ACSM adolescent growth guidelines.
    Returns extra_kcal and extra_prot_g_per_kg to add on top of base RMR targets.
    """
    if sex == "female" and 11 <= age_yr <= 13:
        return {"phv": True, "extra_kcal": 150, "extra_prot_g_per_kg": 0.10}
    if sex == "male" and 13 <= age_yr <= 15:
        return {"phv": True, "extra_kcal": 150, "extra_prot_g_per_kg": 0.10}
    return {"phv": False, "extra_kcal": 0, "extra_prot_g_per_kg": 0.0}


def _cho_intensity_key(norm: str, intensity: Optional[str]) -> str:
    """Map event_type + raw intensity to a CHO_FACTOR key."""
    if norm == "tournament":
        return "hard"  # same tier as a demanding game day — see CHO_FACTOR comment
    if norm == "rest":
        return "rest"
    if intensity == "high":
        return "hard"
    if intensity == "medium":
        return "moderate"
    if intensity == "low":
        return "low"
    return "moderate"


def _duration_bucket(duration_min: float) -> str:
    if duration_min < 60:
        return "lt60"
    if duration_min <= 90:
        return "bt6090"
    return "gt90"


def calc_daily_cho(
    wt_kg: float,
    intensity: str,
    duration_min: float,
    season: str,
    activity_cho_modifier: float = 1.0,
) -> int:
    """Daily carbohydrate target in grams.

    Sources: ACSM/AND Joint Position Statement (Thomas et al. 2016),
             ISSN Nutrient Timing Position Stand (2017).

    activity_cho_modifier from activity_engine.get_activity_profile():
      S&C ×0.85 · speed/game ×1.10 · double-session ×1.25 · others ×1.0
    Two-step rounding matches the dietician spec — base rounded before modifier applied.
    """
    f      = CHO_FACTOR.get(intensity, CHO_FACTOR["moderate"])
    factor = f.get("any") or f.get(_duration_bucket(duration_min), 6.0)
    base   = round(wt_kg * factor * SEASON_CHO.get(season, 1.0))
    return round(base * activity_cho_modifier)


def calc_daily_protein(
    wt_kg: float,
    sport_type: str,
    season: str,
    sex: str,
    diet_pref: str = "omnivore",
    is_sc_day: bool = False,
    phv_extra_g_per_kg: float = 0.0,
) -> int:
    """Daily protein target in grams — flat 7 days/week; S&C and PHV add on top.

    Sources: ISSN Position Stand on Protein (2017); ISSN resistance training standard.
    diet_pref multiplier (+10 % vegetarian / +15 % vegan) corrects for lower leucine
    bioavailability in plant-based diets.
    sex is reserved for future sex-specific adjustments — not applied yet.
    """
    base   = SPORT_PROT.get(sport_type, SPORT_PROT["other"]) * SEASON_PROT.get(season, 1.0)
    sc_add = SC_PROT_BUMP if is_sc_day else 0.0
    return round(
        wt_kg * (base + sc_add + phv_extra_g_per_kg)
        * DIET_PROT_MULT.get(diet_pref, 1.0)
    )


def calc_daily_fat(total_kcal: int, daily_cho_g: int, daily_prot_g: int, sex: str) -> dict:
    """Fat by residual — silent, never shown to athlete (hard rule).

    fat_g    = (TDEE − CHO×4 − Protein×4) ÷ 9, floored at min_fat. On a day whose
               carb+protein prescription already meets or exceeds the calorie
               budget (e.g. a heavy athlete on a short tournament-tagged session —
               tournament's carb factor doesn't scale down for a short session),
               the raw residual can go to zero or negative; the floor guarantees
               fat_g is always a realistic, positive number.
    min_fat  = 25 % of TDEE for females (hormonal health floor), 20 % for males
    max_fat  = 35 % of TDEE for all

    FAT_LOW triggers a parent-dashboard message only — never exposed in athlete UI.
    Fires whenever the floor had to override the raw residual, not just when the
    (now-clamped) fat_g is low — this is the signal that the day's carb+protein
    prescription left no real room for fat, which matters even though the number
    shown is always valid.
    FAT_HIGH is informational for the parent dashboard; not an error.
    """
    fat_kcal  = total_kcal - (daily_cho_g * 4) - (daily_prot_g * 4)
    raw_fat_g = round(fat_kcal / 9)
    min_pct   = 0.25 if sex == "female" else 0.20
    min_fat   = round((total_kcal * min_pct) / 9)
    max_fat   = round((total_kcal * 0.35) / 9)
    fat_g     = max(raw_fat_g, min_fat)
    flag = ("FAT_LOW"  if raw_fat_g < min_fat else
            "FAT_HIGH" if raw_fat_g > max_fat else None)
    return {
        "fat_g":          fat_g,
        "fat_g_min":      min_fat,
        "fat_g_max":      max_fat,
        "fat_flag":       flag,
        "show_to_athlete": False,  # HARD RULE — never expose to teen UI
    }


def estimate_ffm(wt_kg: float, sex: str, age_yr: float, sport_type: str) -> float:
    """Sport/sex/age-stratified fat-free mass estimate (no body comp scan required).

    Endurance sports carry a higher FFM% due to lower body-fat norms for aerobic athletes.
    Age < 14 adjustment: younger athletes have physiologically lower FFM%.
    """
    if sex == "female":
        pct = 0.78 if sport_type in _ENDURANCE_SPORTS else 0.76
    else:
        pct = 0.84 if sport_type in _ENDURANCE_SPORTS else 0.82
    if age_yr < 14:
        pct -= 0.02
    return round(wt_kg * pct, 1)


def check_energy_availability(
    wt_kg: float,
    sex: str,
    age_yr: float,
    sport_type: str,
    daily_cho_g: int,
    daily_prot_g: int,
    daily_fat_g: int,
    exercise_kcal: int,
) -> dict:
    """Energy Availability check — silent, parent-only (athlete_msg always None).

    EA = (dietary kcal − exercise kcal) / FFM kg
    Source: IOC Mountjoy et al. 2023 consensus on Relative Energy Deficiency in Sport.

    Zones:
      RED    — ea < EA_FLOOR[sex]  → notify_parent
      YELLOW — EA_FLOOR ≤ ea < 45  → log_only
      GREEN  — ea ≥ 45             → no action
    """
    ffm    = estimate_ffm(wt_kg, sex, age_yr, sport_type)
    d_kcal = daily_cho_g * 4 + daily_prot_g * 4 + daily_fat_g * 9
    ea     = (d_kcal - exercise_kcal) / ffm
    floor  = EA_FLOOR.get(sex, 30)
    if ea < floor:
        return {"zone": "RED",    "flag": True,  "action": "notify_parent", "athlete_msg": None}
    if ea < EA_OPTIMAL:
        return {"zone": "YELLOW", "flag": True,  "action": "log_only",      "athlete_msg": None}
    return     {"zone": "GREEN",  "flag": False, "action": None,             "athlete_msg": None}


def check_calorie_floor(total_kcal: int, sex: str, age_yr: float, sport_type: str) -> dict:
    """Absolute calorie floor check — silent, parent-only. Not a diagnosis; early-warning signal.

    Base floor: female 1800, male 2000 kcal
    +200 for high-demand sports (soccer, basketball, cross_country, swimming, running, football)
    +100 for age < 14 (higher growth energy cost)
    """
    floor = KCAL_FLOOR.get(sex, 1800)
    if sport_type in _HIGH_DEMAND:
        floor += 200
    if age_yr < 14:
        floor += 100
    if total_kcal < floor:
        return {"flag": True, "action": "log_and_notify_parent", "athlete_msg": None}
    return {"flag": False}


def calc_hydration(
    wt_kg: float,
    sport_type: str,
    duration_min: float,
    sex: str,
    is_outdoor: bool = False,
    temp_f: float = 70,
    humidity_pct: float = 50,
) -> dict:
    """Sport/environment/sex-adjusted daily hydration target.

    baseline_oz = post-exercise (4 mL/kg → oz) + 27 oz pre-exercise floor
    during_oz   = 80% of sweat loss (sweat_rate × env_mult × hours × 33.8 oz/L)
    female_add  = +8 oz/day luteal-phase baseline (always-on; GSSI 2020)
    total_daily_oz = baseline_oz + during_oz + female_add

    Environmental multipliers stack: heat × humid; cold applies independently.
    """
    baseline_oz = round(4 * wt_kg / 29.6) + 27
    sweat_rate  = SWEAT_RATE.get(sport_type, 1.00)
    env = 1.0
    if is_outdoor:
        if temp_f >= 80:
            env *= HEAT_MULT
        if humidity_pct > 70:
            env *= HUMID_MULT
    if temp_f < 50:
        env *= COLD_MULT
    hours        = duration_min / 60
    loss_oz      = round(sweat_rate * env * hours * 33.8)
    during_oz    = round(loss_oz * 0.80)
    per_30min_oz = round(during_oz / max(hours * 2, 1))
    female_add   = FEMALE_HYD_ADD_OZ if sex == "female" else 0
    total_oz     = baseline_oz + during_oz + female_add
    swimming_note = (
        "Even though you are in the water, your body is still sweating. "
        "Drink before and after practice even if you do not feel thirsty."
        if sport_type == "swimming" else None
    )
    return {
        "total_daily_oz":  total_oz,
        "baseline_oz":     baseline_oz,
        "during_oz":       during_oz,
        "per_30min_oz":    per_30min_oz,
        "swimming_note":   swimming_note,
    }


def get_iron_flag(sex: str, sport_type: str, diet_pref: str) -> bool:
    """True = trigger iron-rich food suggestions in the Recharge window.

    All female athletes, all vegan athletes, and endurance-sport males all face
    elevated iron-depletion risk. Source: GSSI Female Athlete (2020), IOC REDs (2023).

    POST-MVP: amplify during menstruation days 1–5 when cycle tracking is added.
    """
    if sex == "female":
        return True
    if diet_pref == "vegan":
        return True
    if sport_type in _IRON_ENDURANCE:
        return True
    return False


def _sport_type_from_event(norm: str) -> str:
    if norm == "strength":
        return "strength"
    return "soccer"


def _normalize_season(season_phase: Optional[str]) -> str:
    if not season_phase:
        return "in_season"
    s = season_phase.lower().strip()
    if s in ("postseason", "post_season"):
        return "post_season"
    if s == "off_season":
        return "off_season"
    return "in_season"


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
    wt_kg  = lbs_to_kg(athlete["weight_lbs"])
    ht_cm  = ft_in_to_cm(athlete["height_ft"], athlete["height_in"])
    sex    = _normalize_sex(athlete["gender"])
    age_yr = calc_age(
        dob_str=athlete.get("date_of_birth"),
        age_fallback=athlete.get("age"),
    )

    rmr  = calc_rmr(wt_kg, ht_cm, sex, age_yr)
    phv  = check_growth_phase(age_yr, sex)
    norm = normalize_event_type(event_type)

    pal = PAL.get(athlete.get("lifestyle_activity", "light"), 1.4)
    # An explicit resolved activity_type (the athlete's per-event tag) overrides the
    # event_type-derived profile, so the per-type modifiers apply: speed_sprint ×1.10,
    # strength_cond is_sc_day, active_recovery rest-level CHO, double_session ×1.25.
    # Falls back to the event_type-derived activity type when not supplied/invalid.
    profile_key = activity_type if activity_type in VALID_ACTIVITY_TYPES else _to_activity_type(norm)
    act = get_activity_profile(profile_key, intensity, duration_min, wt_kg)

    total_calories = calc_tdee(rmr, pal, act["aee_kcal"], phv["extra_kcal"])

    # ── Spec-formula CHO target ───────────────────────────────────────────────
    season = _normalize_season(athlete.get("season_phase"))
    # intensity_override from activity engine takes precedence over caller-supplied intensity
    cho_intensity = (act["intensity_override"] if act["intensity_override"] in CHO_FACTOR
                     else _cho_intensity_key(norm, intensity))
    carbs_g = calc_daily_cho(wt_kg, cho_intensity, duration_min, season, act["cho_modifier"])

    # ── Spec-formula protein target ───────────────────────────────────────────
    diet_pref  = athlete.get("diet_pref") or "omnivore"
    sport_type = _sport_type_from_event(norm)
    protein_g  = calc_daily_protein(
        wt_kg,
        sport_type,
        season,
        sex,
        diet_pref=diet_pref,
        is_sc_day=act["is_sc_day"],
        phv_extra_g_per_kg=phv["extra_prot_g_per_kg"],
    )

    # ── Spec-formula hydration target (oz) ───────────────────────────────────
    hyd = calc_hydration(wt_kg, sport_type, duration_min, sex,
                         is_outdoor=is_outdoor, temp_f=temp_f, humidity_pct=humidity_pct)
    hydration_oz = hyd["total_daily_oz"]

    # ── Legacy range fields (kept for DB schema & other callers) ─────────────
    carb_lo, carb_hi = CARB_TARGETS[norm]
    prot_lo, prot_hi = PROTEIN_TARGETS[norm]
    if intensity:
        carb_lo, carb_hi = _reposition(carb_lo, carb_hi, intensity)
        prot_lo, prot_hi = _reposition(prot_lo, prot_hi, intensity)
    fat     = calc_daily_fat(total_calories, carbs_g, protein_g, sex)

    iron_mg   = 15 if sex == "female" else 11
    iron_flag = get_iron_flag(sex, sport_type, diet_pref)
    calcium_mg = 1300

    ea_check   = check_energy_availability(
        wt_kg, sex, age_yr, sport_type,
        carbs_g, protein_g, fat["fat_g"],
        exercise_kcal=act["aee_kcal"],
    )
    kcal_check = check_calorie_floor(total_calories, sex, age_yr, sport_type)

    return {
        "event_type": norm,
        "intensity": intensity,
        "total_calories": total_calories,
        # Spec single-value targets (used by Today dashboard)
        "carbs_g": carbs_g,
        "protein_g": protein_g,
        "hydration_oz":         hydration_oz,
        "hydration_baseline_oz": hyd["baseline_oz"],
        "hydration_during_oz":   hyd["during_oz"],
        "hydration_per_30min_oz": hyd["per_30min_oz"],
        "hydration_swimming_note": hyd["swimming_note"],
        # Fat — residual; silent (show_to_athlete always False)
        "fat_g":          fat["fat_g"],
        "fat_g_min":      fat["fat_g_min"],
        "fat_g_max":      fat["fat_g_max"],
        "fat_flag":       fat["fat_flag"],
        "show_to_athlete": False,
        # Micronutrients
        "iron_mg":   iron_mg,
        "iron_flag": iron_flag,
        "calcium_mg": calcium_mg,
        # Legacy range fields (DB storage, reports)
        "carbs_g_min": carbs_g,
        "carbs_g_max": carbs_g,
        "protein_g_min": protein_g,
        "protein_g_max": protein_g,
        "hydration_oz_min": hydration_oz,
        "hydration_oz_max": hydration_oz,
        # Energy availability — parent-only, athlete_msg always None
        "ea_zone":   ea_check["zone"],
        "ea_flag":   ea_check["flag"],
        "ea_action": ea_check["action"],
        "lea_alert": ea_check["flag"],   # backward compat — Blueprint LEAWarning component
        # Absolute calorie floor — conservative early-warning, parent-only
        "kcal_floor_flag":   kcal_check["flag"],
        "kcal_floor_action": kcal_check.get("action"),
    }


def calculate_daily_targets(athlete: dict, session: dict, weather: dict) -> dict:
    """Master function — call once per day when calendar events are loaded.

    Returns complete daily targets for the Today dashboard, fueling windows,
    and parent dashboard. Uses clean pre-processed input dicts rather than
    a raw DB row (see calc_daily_targets() for the DB-row adapter).

    athlete = {
        'dob': 'YYYY-MM-DD', 'sex': 'female'|'male',
        'wt_kg': float, 'ht_cm': float,
        'sport_type': str,            # e.g. 'soccer', 'running', 'strength'
        'season': str,                # in_season|off_season|postseason
        'pal_key': 'sedentary'|'light'|'moderate',  # default 'light'
        'diet_pref': str,             # omnivore|vegetarian|vegan
        'allergies': list,            # informational; not used in calculations
    }
    session = {
        'activity_type': str,   # from activity_engine MET_VALUES keys
        'intensity': str,       # rest|low|moderate|hard|tournament
        'duration_min': int,
        'is_outdoor': bool,
    }
    weather = {'temp_f': float, 'humidity_pct': float}
    """
    age = calc_age(dob_str=athlete["dob"])
    phv = check_growth_phase(age, athlete["sex"])
    rmr = calc_rmr(athlete["wt_kg"], athlete["ht_cm"], athlete["sex"], age)
    pal = PAL.get(athlete.get("pal_key", "light"), 1.4)

    act  = get_activity_profile(
        session["activity_type"],
        session["intensity"],
        session["duration_min"],
        wt_kg=athlete["wt_kg"],   # required for AEE — omitted in spec but needed
    )

    tdee = calc_tdee(rmr, pal, act["aee_kcal"], phv["extra_kcal"])

    cho_intensity = act["intensity_override"] or session["intensity"]
    cho  = calc_daily_cho(
        athlete["wt_kg"], cho_intensity, session["duration_min"],
        athlete["season"], act["cho_modifier"],
    )

    prot = calc_daily_protein(
        athlete["wt_kg"], athlete["sport_type"], athlete["season"], athlete["sex"],
        diet_pref=athlete["diet_pref"],
        is_sc_day=act["is_sc_day"],
        phv_extra_g_per_kg=phv["extra_prot_g_per_kg"],
    )

    fat  = calc_daily_fat(tdee, cho, prot, athlete["sex"])

    ea   = check_energy_availability(
        athlete["wt_kg"], athlete["sex"], age, athlete["sport_type"],
        cho, prot, fat["fat_g"], act["aee_kcal"],
    )

    kcal_flag = check_calorie_floor(tdee, athlete["sex"], age, athlete["sport_type"])

    hyd  = calc_hydration(
        athlete["wt_kg"], athlete["sport_type"], session["duration_min"], athlete["sex"],
        is_outdoor=session["is_outdoor"],
        temp_f=weather["temp_f"],
        humidity_pct=weather["humidity_pct"],
    )

    iron = get_iron_flag(athlete["sex"], athlete["sport_type"], athlete["diet_pref"])

    return {
        "daily": {
            "cho_g":   cho,
            "prot_g":  prot,
            "fat_g":   fat["fat_g"],
            "hyd_oz":  hyd["total_daily_oz"],
            "kcal":    tdee,
        },
        "meta": {
            "age":      age,
            "rmr":      rmr,
            "pal":      pal,
            "phv":      phv["phv"],
            "act_type": session["activity_type"],
        },
        "flags": {
            "ea":   ea,
            "kcal": kcal_flag,
            "fat":  fat["fat_flag"],   # spec uses fat['flag']; our key is fat_flag
            "iron": iron,
        },
        "hyd_detail":          hyd,
        "fat_show_to_athlete": False,  # hard rule
    }
