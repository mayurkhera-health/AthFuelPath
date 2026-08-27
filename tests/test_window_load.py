from api.services.window_load import bucket_level, fat_level_for, load_levels_for


def test_bucket_level_high_at_or_above_point_25():
    assert bucket_level(0.25) == "HIGH"
    assert bucket_level(0.40) == "HIGH"


def test_bucket_level_moderate_between_point_13_and_point_25():
    assert bucket_level(0.13) == "MODERATE"
    assert bucket_level(0.22) == "MODERATE"


def test_bucket_level_light_below_point_13():
    assert bucket_level(0.10) == "LIGHT"
    assert bucket_level(0.0) == "LIGHT"


def test_bucket_level_none_defaults_to_moderate():
    assert bucket_level(None) == "MODERATE"


def test_fat_level_by_category_key():
    assert fat_level_for("carb") == "LIGHT"
    assert fat_level_for("hydrate") == "LIGHT"
    assert fat_level_for("balanced") == "MODERATE"
    assert fat_level_for("recovery") == "MODERATE"


def test_fat_level_unknown_category_defaults_to_moderate():
    assert fat_level_for("mystery") == "MODERATE"
    assert fat_level_for(None) == "MODERATE"


def test_load_levels_for_combines_carb_protein_and_fat():
    levels = load_levels_for({"carbs_pct": 0.35, "protein_pct": 0.15}, "carb")
    assert levels == {"carbs": "HIGH", "protein": "MODERATE", "fats": "LIGHT"}


def test_load_levels_for_missing_pct_dict():
    levels = load_levels_for(None, "recovery")
    assert levels == {"carbs": "MODERATE", "protein": "MODERATE", "fats": "MODERATE"}
