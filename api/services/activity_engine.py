# MET values — ACSM Compendium of Physical Activities (Ainsworth et al. 2011)
MET_VALUES = {
    "practice":         8.0,
    "game":            10.0,
    "tournament":      10.0,
    "speed_sprint":    10.0,
    "strength_cond":    5.0,
    "active_recovery":  2.5,
    "double_session":   9.0,   # average of two sessions
}

_PROFILES = {
    "practice":        {"cho_modifier": 1.00, "intensity_override": None,
                        "is_sc_day": False, "layout": "standard"},
    "game":            {"cho_modifier": 1.10, "intensity_override": "hard",
                        "is_sc_day": False, "layout": "standard"},
    # Same carb tier as a demanding game day (intensity_override "hard", same
    # cho_modifier as "game") — a tournament's carb target used to be a flat
    # 10 g/kg regardless of actual session length, disconnected from the
    # calorie budget a short session actually generates. layout stays
    # "tournament": the window-engine's multi-game scheduling is unaffected,
    # only the nutrition math changed.
    "tournament":      {"cho_modifier": 1.10, "intensity_override": "hard",
                        "is_sc_day": False, "layout": "tournament"},
    "speed_sprint":    {"cho_modifier": 1.10, "intensity_override": "hard",
                        "is_sc_day": False, "layout": "standard"},
    "strength_cond":   {"cho_modifier": 0.85, "intensity_override": "moderate",
                        "is_sc_day": True,  "layout": "standard"},
    "active_recovery": {"cho_modifier": 1.00, "intensity_override": "rest",
                        "is_sc_day": False, "layout": "rest"},
    "double_session":  {"cho_modifier": 1.25, "intensity_override": None,
                        "is_sc_day": False, "layout": "standard"},
}


def get_activity_profile(activity_type: str, intensity: str, duration_min: float, wt_kg: float = 0) -> dict:
    """Return the 4 outputs consumed by calc_daily_targets().

    aee_kcal        — Activity Energy Expenditure (kcal); 0 when wt_kg not provided.
    cho_modifier    — Multiplied onto the base CHO target (×0.85 – ×1.25).
    intensity_override — Forces the CHO_FACTOR row; None means use the caller's intensity.
    is_sc_day       — True for Strength & Conditioning; shifts protein priority.
    layout          — 'standard' | 'tournament' | 'rest'; drives window-engine layout.
    met             — Raw MET value for the session type.
    """
    met   = MET_VALUES.get(activity_type, MET_VALUES["practice"])
    hours = duration_min / 60
    aee   = round(met * wt_kg * hours) if wt_kg else 0
    p     = _PROFILES.get(activity_type, _PROFILES["practice"])
    return {**p, "aee_kcal": aee, "met": met}
