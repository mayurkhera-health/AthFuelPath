"""Unit tests for intensity derivation and band repositioning in nutrition_calc."""

from api.services import nutrition_calc as nc


# ---- derive_intensity ----

def test_rest_event_floors_to_low_even_for_elite():
    assert nc.derive_intensity("Yoga/Flexibility/Recovery", "elite_club") == "low"
    assert nc.derive_intensity("rest", "elite_club") == "low"

def test_elite_club_competitive_event_is_high():
    assert nc.derive_intensity("game", "elite_club") == "high"

def test_competitive_club_is_medium():
    assert nc.derive_intensity("game", "competitive_club") == "medium"

def test_recreational_is_low():
    assert nc.derive_intensity("game", "recreational") == "low"

def test_non_canonical_values_are_not_inferred_as_a_tier():
    """MVP stance: no substring/keyword inference. A legacy display-style
    label or a club/team name is invalid data, not a recognized tier — it
    must fall back to low, the same as any other unclassified value, never
    be guessed at."""
    assert nc.derive_intensity("game", "Elite") == "low"
    assert nc.derive_intensity("game", "Club") == "low"
    assert nc.derive_intensity("game", "Competitive") == "low"
    assert nc.derive_intensity("game", "Elite Club") == "low"
    assert nc.derive_intensity("game", "Bay Area Surf") == "low"

def test_null_competition_level_defaults_low():
    assert nc.derive_intensity("game", None) == "low"
    assert nc.derive_intensity("game", "") == "low"
    assert nc.derive_intensity("game", "something weird") == "low"


# ---- repositioning in calc_daily_targets ----

ATH = {"weight_lbs": 110.23123, "height_ft": 5, "height_in": 6, "gender": "girl", "age": 14}
# 110.23123 lbs -> ~50 kg, age 14 girl

def test_cho_target_is_single_value():
    # Spec-formula CHO is a single value: the legacy band fields collapse to it.
    t = nc.calc_daily_targets(ATH, "practice")
    assert t["carbs_g_min"] == t["carbs_g"] == t["carbs_g_max"]

def test_low_intensity_is_lower_than_medium():
    low = nc.calc_daily_targets(ATH, "practice", intensity="low")
    med = nc.calc_daily_targets(ATH, "practice", intensity="medium")
    assert low["carbs_g"] < med["carbs_g"]

def test_medium_intensity_matches_no_intensity_baseline():
    med  = nc.calc_daily_targets(ATH, "practice", intensity="medium")
    base = nc.calc_daily_targets(ATH, "practice")  # no intensity
    assert med["carbs_g"] == base["carbs_g"]

def test_high_intensity_is_higher_than_medium():
    med  = nc.calc_daily_targets(ATH, "practice", intensity="medium")
    high = nc.calc_daily_targets(ATH, "practice", intensity="high")
    assert high["carbs_g"] > med["carbs_g"]

def test_game_overrides_intensity_to_hard():
    # Game day forces "hard" CHO intensity via the activity engine, so the
    # caller-supplied intensity must NOT change the carb target on a game day.
    low  = nc.calc_daily_targets(ATH, "game", intensity="low")
    high = nc.calc_daily_targets(ATH, "game", intensity="high")
    assert low["carbs_g"] == high["carbs_g"]

def test_intensity_carbs_stay_within_science_bounds():
    # Across all practice intensities the carb target stays in a sane g/kg range.
    wt_kg = nc.lbs_to_kg(ATH["weight_lbs"])
    for intensity in ("low", "medium", "high"):
        t = nc.calc_daily_targets(ATH, "practice", intensity=intensity)
        g_per_kg = t["carbs_g"] / wt_kg
        assert 2.0 <= g_per_kg <= 12.0


def test_activity_type_override_drives_profile():
    base = nc.calc_daily_targets(ATH, "practice")
    over = nc.calc_daily_targets(ATH, "practice", activity_type="game")
    assert over["carbs_g"] > base["carbs_g"]


def test_activity_type_active_recovery_gives_rest_cho():
    wt = nc.lbs_to_kg(ATH["weight_lbs"])
    t = nc.calc_daily_targets(ATH, "practice", activity_type="active_recovery")
    assert round(t["carbs_g"] / wt) == 4


def test_activity_type_strength_cond_sets_sc_protein_bump():
    practice = nc.calc_daily_targets(ATH, "practice")
    sc = nc.calc_daily_targets(ATH, "practice", activity_type="strength_cond")
    assert sc["protein_g"] >= practice["protein_g"]


def test_invalid_activity_type_falls_back_to_event_type():
    a = nc.calc_daily_targets(ATH, "game", activity_type="bogus")
    b = nc.calc_daily_targets(ATH, "game")
    assert a["carbs_g"] == b["carbs_g"]


def test_no_activity_type_unchanged():
    a = nc.calc_daily_targets(ATH, "game")
    b = nc.calc_daily_targets(ATH, "game", activity_type=None)
    assert a == b


# ---- calc_daily_fat floor ----
# A heavy athlete on a short tournament-tagged session: tournament's carb factor
# is a flat 10 g/kg regardless of duration, so a SHORT session prescribes a
# full-tournament carb load without the calorie budget (AEE) a longer day would
# generate to pay for it. Real repro, run through the live code:
# 210 lb / 6'2" 16-year-old boy, tournament, 60-minute session.
HEAVY_ATH = {"weight_lbs": 210, "height_ft": 6, "height_in": 2, "gender": "boy", "age": 16}


def test_fat_never_goes_negative_on_the_real_tournament_repro():
    t = nc.calc_daily_targets(HEAVY_ATH, event_type="tournament", duration_min=60,
                               activity_type="tournament")
    assert t["fat_g"] >= 0
    assert t["fat_g"] == t["fat_g_min"], "Floor should be the binding constraint here"
    assert t["fat_flag"] == "FAT_LOW", "Flag must still fire even though fat_g is now clamped positive"


def test_calc_daily_fat_clamps_a_negative_residual_to_the_floor():
    # total_kcal deliberately too low for the given carb+protein grams — the raw
    # residual is negative — floor must win, not the raw (negative) computation.
    fat = nc.calc_daily_fat(total_kcal=2000, daily_cho_g=400, daily_prot_g=150, sex="male")
    raw_residual_g = round((2000 - 400 * 4 - 150 * 4) / 9)
    assert raw_residual_g < 0, "Test setup should produce a negative raw residual"
    assert fat["fat_g"] == fat["fat_g_min"]
    assert fat["fat_g"] > 0
    assert fat["fat_flag"] == "FAT_LOW"


def test_calc_daily_fat_unclamped_case_is_unaffected():
    # A normal day where the residual comfortably clears the floor (and stays
    # under the ceiling) — clamping must be a no-op, not change correct output.
    fat = nc.calc_daily_fat(total_kcal=2800, daily_cho_g=350, daily_prot_g=130, sex="male")
    raw_residual_g = round((2800 - 350 * 4 - 130 * 4) / 9)
    assert fat["fat_g_min"] <= raw_residual_g <= fat["fat_g_max"]
    assert fat["fat_g"] == raw_residual_g
    assert fat["fat_flag"] is None


def test_calc_daily_fat_high_flag_still_fires_above_the_ceiling():
    # FAT_HIGH path must be untouched by the floor change.
    fat = nc.calc_daily_fat(total_kcal=3000, daily_cho_g=100, daily_prot_g=50, sex="male")
    assert fat["fat_flag"] == "FAT_HIGH"


# ---- tournament carb-factor fix (Purvi, 2026-07-27) ----
# The event-type LABEL "tournament" used to force a flat 10 g/kg carb factor
# regardless of actual session length or measured intensity — higher than even
# a "hard" game day (8 g/kg). Tournament now shares the exact same tier as a
# demanding game day.

def test_tournament_no_longer_gets_a_higher_carb_factor_than_game():
    game = nc.calc_daily_targets(HEAVY_ATH, event_type="game", duration_min=60,
                                  activity_type="game")
    tournament = nc.calc_daily_targets(HEAVY_ATH, event_type="tournament", duration_min=60,
                                        activity_type="tournament")
    assert tournament["carbs_g"] == game["carbs_g"]


def test_tournament_carb_factor_is_no_longer_the_old_flat_10_g_per_kg():
    wt_kg = nc.lbs_to_kg(HEAVY_ATH["weight_lbs"])
    t = nc.calc_daily_targets(HEAVY_ATH, event_type="tournament", duration_min=60,
                               activity_type="tournament")
    g_per_kg = t["carbs_g"] / wt_kg
    assert g_per_kg < 10.0


def test_double_training_day_no_longer_maps_to_tournament():
    # "double training day" was mapped to the "tournament" event-type bucket,
    # inheriting its (now-removed) inflated carb tier despite being two
    # practice/training sessions, not a multi-game tournament.
    assert nc.normalize_event_type("double training day") != "tournament"
    assert nc.normalize_event_type("double training day") == "training"


# ---- calc_age ----

def test_calc_age_computes_from_valid_dob():
    assert nc.calc_age(dob_str="2010-06-15", age_fallback=None) == float(
        nc.date.today().year - 2010 - ((nc.date.today().month, nc.date.today().day) < (6, 15))
    )


def test_calc_age_falls_back_on_malformed_dob_instead_of_raising():
    # A malformed date_of_birth (e.g. saved via an admin route with no format
    # check) used to raise an uncaught ValueError here, 500ing every route
    # that computes age for that athlete (e.g. Blueprint).
    assert nc.calc_age(dob_str="06/15/2010", age_fallback=15) == 15.0


def test_calc_age_raises_when_dob_malformed_and_no_fallback():
    import pytest
    with pytest.raises(ValueError):
        nc.calc_age(dob_str="not-a-date", age_fallback=None)
