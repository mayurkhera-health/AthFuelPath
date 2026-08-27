"""Deterministic HIGH/MODERATE/LIGHT load-level labels for Today's fueling
window cards. Reuses the existing _FOCUS_MACRO_PCT carbs_pct/protein_pct
splits (today_service.py) as the single source of truth for carb/protein
load — no new arbitrary UI thresholds. Fat has no numeric contribution
anywhere in the fuel pipeline (see fueling_targets.NUTRIENT_KEYS), so fat
load is derived from the window's category_key instead.
"""

FAT_LEVEL_BY_CATEGORY_KEY = {
    "carb":     "LIGHT",
    "hydrate":  "LIGHT",
    "balanced": "MODERATE",
    "recovery": "MODERATE",
}


def bucket_level(pct):
    if pct is None:
        return "MODERATE"
    if pct >= 0.25:
        return "HIGH"
    if pct >= 0.13:
        return "MODERATE"
    return "LIGHT"


def fat_level_for(category_key):
    return FAT_LEVEL_BY_CATEGORY_KEY.get(category_key or "", "MODERATE")


def load_levels_for(focus_pct, category_key):
    focus_pct = focus_pct or {}
    return {
        "carbs":   bucket_level(focus_pct.get("carbs_pct")),
        "protein": bucket_level(focus_pct.get("protein_pct")),
        "fats":    fat_level_for(category_key),
    }
