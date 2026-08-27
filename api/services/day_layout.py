"""
Day Layout Engine — Today-tab fuel-window card ordering (Purvi spec).

Produces the ordered card list for a day from its events + resolved activity
types. Reuses window_engine_v2 timing primitives; grams are overlaid downstream.
Replaces window_engine_v2 as the Today-tab window source (behind DAY_LAYOUT_V2).

Public API: build_day_layout(events, athlete, now) -> {"day_type", "cards"}
"""

import os
from datetime import datetime, time, timedelta

from api.services.activity_type_resolver import resolve_activity_type
from api.services.tournament_template import get_tournament_template
from api.services import window_engine_v2 as wev2
from api.services.window_distribution import keep_going_window

REST_MEAL_TIMES = {"breakfast": "07:30", "lunch": "12:30", "dinner": "18:30"}
EVENING_WIND_DOWN_AFTER = time(20, 0)  # event end past 8:00 PM -> optional wind-down card


def _as_wev2_event(ev: dict):
    """Adapt a plain event dict to the attribute access wev2 timing helpers expect."""
    return wev2.Event(
        id=ev.get("id", 0), athlete_id=ev.get("athlete_id", 0),
        event_type=ev["event_type"], event_date=ev["event_date"],
        start_time=ev["start_time"], duration_hours=ev.get("duration_hours"),
    )


def _rest_meal_cards() -> list:
    """Breakfast/Lunch/Dinner rest-style cards (33/34/33 split applied downstream)."""
    cards = []
    for kind in ("breakfast", "lunch", "dinner"):
        t = REST_MEAL_TIMES[kind]
        cards.append({
            "key": kind, "card": kind, "label": kind.capitalize(),
            "is_event": False, "is_tappable": True,
            "sort_time": t, "time_display": "", "game_num": None, "duration_min": None,
        })
    return cards


def _standard_single_event_cards(ev: dict, start_dt: datetime, end_dt: datetime) -> list:
    """Spec order for a single non-tournament event. everyday_meal placement flips
    on the 11:00 boundary; keep_going only when duration > 75 min."""
    dur_min = int(round((ev.get("duration_hours") or 1.5) * 60))
    morning = start_dt.hour < 11

    def card(key, kind, sort_dt, label, is_event=False, duration_min=None):
        return {"key": key, "card": kind, "label": label,
                "is_event": is_event, "is_tappable": not is_event,
                "sort_time": wev2._hhmm(sort_dt), "time_display": "",
                "game_num": None, "duration_min": duration_min}

    if morning:
        everyday_sort = end_dt + timedelta(hours=2)          # after rebuild → sorts LAST
    else:
        everyday_sort = start_dt.replace(hour=7, minute=30)  # earliest → sorts FIRST
    everyday = card("everyday_meal", "everyday_meal", everyday_sort, "Everyday Meal")

    core = [
        card("fuel_before", "fuel_before", start_dt - timedelta(hours=3), "Fuel Before"),
        card("top_up", "top_up", start_dt - timedelta(minutes=45), "Top-Up"),
        card("event", "event", start_dt,
             ev.get("event_name") or ev["event_type"].capitalize(),
             is_event=True, duration_min=dur_min),
    ]
    if dur_min > 75:
        core.append(card("keep_going", "keep_going", start_dt + timedelta(minutes=dur_min // 2),
                         "Keep Going", duration_min=dur_min))
    core += [
        card("recharge", "recharge", end_dt, "Recharge"),
        card("rebuild", "rebuild", end_dt + timedelta(hours=1), "Rebuild"),
    ]

    # everyday placement: morning -> last, afternoon/evening -> first
    return core + [everyday] if morning else [everyday] + core


def _double_session_cards(
    ev1: dict, ev2: dict,
    start_dt1: datetime, end_dt1: datetime,
    start_dt2: datetime, end_dt2: datetime,
) -> list:
    """Layout for two non-tournament events on the same day (e.g. morning practice +
    afternoon training). The cap is disabled by the caller — double sessions
    legitimately need more cards than a single-event day.

    Pattern:
      Fuel Before → Top-Up → Event 1 → [Keep Going] → Recharge
      → Everyday Meal (lunch in gap) → Event 2 → [Keep Going] → Rebuild
    """
    dur_min1 = int(round((ev1.get("duration_hours") or 1.5) * 60))
    dur_min2 = int(round((ev2.get("duration_hours") or 1.5) * 60))

    def card(key, kind, sort_dt, label, is_event=False, duration_min=None):
        return {"key": key, "card": kind, "label": label,
                "is_event": is_event, "is_tappable": not is_event,
                "sort_time": wev2._hhmm(sort_dt), "time_display": "",
                "game_num": None, "duration_min": duration_min}

    cards = [
        card("fuel_before", "fuel_before", start_dt1 - timedelta(hours=3), "Fuel Before"),
        card("top_up",      "top_up",      start_dt1 - timedelta(minutes=45), "Top-Up"),
        card("event_1",     "event",       start_dt1,
             ev1.get("event_name") or ev1["event_type"].capitalize(),
             is_event=True, duration_min=dur_min1),
    ]
    if dur_min1 > 75:
        cards.append(card("keep_going_1", "keep_going",
                          start_dt1 + timedelta(minutes=dur_min1 // 2),
                          "Keep Going", duration_min=dur_min1))

    cards.append(card("recharge", "recharge", end_dt1, "Recharge"))

    # Everyday meal anchored 1h after session 1 ends — lunch in the gap.
    cards.append(card("everyday_meal", "everyday_meal",
                      end_dt1 + timedelta(hours=1), "Everyday Meal"))

    cards += [
        card("event_2", "event", start_dt2,
             ev2.get("event_name") or ev2["event_type"].capitalize(),
             is_event=True, duration_min=dur_min2),
    ]
    if dur_min2 > 75:
        cards.append(card("keep_going_2", "keep_going",
                          start_dt2 + timedelta(minutes=dur_min2 // 2),
                          "Keep Going", duration_min=dur_min2))

    cards.append(card("rebuild", "rebuild", end_dt2 + timedelta(hours=1), "Rebuild"))
    return cards


MAX_TAPPABLE = wev2.MAX_TAPPABLE_WINDOWS  # 6


# Structural anchor cards exempt from the tappable cap (besides event markers,
# which are non-tappable). wind_down is the mandatory end-of-day recommendation.
_CAP_EXEMPT_CARDS = {"wind_down"}


def _apply_guardrails(cards: list, cap: bool = True) -> list:
    """Port of window_engine_v2 guardrails to the new card list, ORDER-PRESERVING:
      1. Floor (always): no card sort_time before 06:30.
      2. Cap (only when cap=True): at most MAX_TAPPABLE tappable cards, dropping
         excess from the end. Event markers and wind_down are never dropped.

    The cap is applied ONLY to the standard single-event path, where MAX_TAPPABLE
    is the natural ceiling. It is NOT applied to tournament days: Purvi's tournament
    template deliberately produces many cards, and dropping from the end there would
    delete the post-tournament Recharge/Rebuild recovery meals. Rest/active-recovery
    days (3 cards) are well under the cap regardless.

    Dedup (15-min) is intentionally NOT applied — the spec's card order is a
    deliberate scroll order; collisions are resolved by the floor only.
    """
    floor = wev2.DISPLAY_FLOOR.strftime("%H:%M")
    for c in cards:
        if c["sort_time"] and c["sort_time"] < floor:
            c["sort_time"] = floor

    if not cap:
        return cards

    tappable_seen = 0
    kept = []
    for c in cards:
        if c["is_tappable"] and c["card"] not in _CAP_EXEMPT_CARDS:
            if tappable_seen >= MAX_TAPPABLE:
                continue
            tappable_seen += 1
        kept.append(c)
    return kept


def _attach_keep_going_labels(cards: list, wt_kg: float) -> list:
    """Attach the athlete-facing oz/packets label to keep_going cards (never grams)."""
    for c in cards:
        if c["card"] == "keep_going" and c.get("duration_min"):
            kg = keep_going_window(wt_kg, c["duration_min"])
            if kg:
                c["athlete_label"] = kg["athlete_label"]
    return cards


def build_day_layout(events: list, athlete: dict, now: datetime) -> dict:
    """Return {"day_type": str, "cards": [card, ...]} for the athlete's day.

    events: rows for the target date (each a dict with event_type, activity_type,
            event_date, start_time, duration_hours).
    """
    # Resolve each event's effective activity type (2-hour default).
    resolved = []
    for ev in events:
        at = resolve_activity_type(ev, now)
        resolved.append((ev, at))

    wt_kg_for_labels = athlete["weight_lbs"] * 0.453592 if athlete.get("weight_lbs") else 0

    # Rest day — no events at all.
    if not resolved:
        return {"day_type": "rest", "cards": _attach_keep_going_labels(_apply_guardrails(_rest_meal_cards(), cap=False), wt_kg_for_labels)}

    # Active Recovery / Yoga -> rest-style 3 meals regardless of time.
    if any(at == "active_recovery" for _, at in resolved):
        return {"day_type": "active_recovery", "cards": _attach_keep_going_labels(_apply_guardrails(_rest_meal_cards(), cap=False), wt_kg_for_labels)}

    # Tournament: explicit tournament tag, OR >= 2 game/tournament events same day.
    game_like = [(ev, at) for ev, at in resolved
                 if at in ("game", "tournament") or ev["event_type"] in ("game", "tournament")]
    is_tournament = (
        any(at == "tournament" for _, at in resolved)
        or len(game_like) >= 2
    )
    if is_tournament:
        schedule = sorted(
            ({"start_time": ev["start_time"],
              "duration_min": int(round((ev.get("duration_hours") or 1.5) * 60))}
             # Only game/tournament events form the game schedule — a non-game event
             # on a tournament day (e.g. a morning lift) must NOT become a fake game slot.
             for ev, _ in game_like if ev.get("start_time")),
            key=lambda g: g["start_time"],
        )
        wt_kg = athlete["weight_lbs"] * 0.453592 if athlete.get("weight_lbs") else 0
        cards = get_tournament_template(schedule, wt_kg)
        # No cap on tournaments — the template's many cards (incl. post-tournament
        # Recharge/Rebuild) are all deliberate and must survive.
        return {"day_type": "tournament", "cards": _attach_keep_going_labels(_apply_guardrails(cards, cap=False), wt_kg_for_labels)}

    # Double session: 2+ events on the same day (not tournament).
    if len(resolved) >= 2:
        sorted_sessions = sorted(resolved, key=lambda t: t[0].get("start_time") or "")
        ev1, _ = sorted_sessions[0]
        ev2, _ = sorted_sessions[1]
        start_dt1 = wev2._parse_start(_as_wev2_event(ev1))
        end_dt1   = wev2._event_end(_as_wev2_event(ev1), start_dt1)
        start_dt2 = wev2._parse_start(_as_wev2_event(ev2))
        end_dt2   = wev2._event_end(_as_wev2_event(ev2), start_dt2)
        cards = _double_session_cards(ev1, ev2, start_dt1, end_dt1, start_dt2, end_dt2)
        return {"day_type": "double_session",
                "cards": _attach_keep_going_labels(_apply_guardrails(cards, cap=False), wt_kg_for_labels)}

    # Single non-tournament event -> standard layout.
    primary_ev, _ = resolved[0]
    start_dt = wev2._parse_start(_as_wev2_event(primary_ev))
    end_dt = wev2._event_end(_as_wev2_event(primary_ev), start_dt)
    cards = _standard_single_event_cards(primary_ev, start_dt, end_dt)
    if not athlete.get("wind_down_dismissed") and end_dt.time() > EVENING_WIND_DOWN_AFTER:
        cards.append({
            "key": "wind_down", "card": "wind_down", "label": "Evening Wind-Down",
            "is_event": False, "is_tappable": True,
            # Sorts after rebuild (end + 1h) so it stays last by sort_time, matching
            # its list position ("appended at the end" per spec).
            "sort_time": wev2._hhmm(end_dt + timedelta(minutes=90)), "time_display": "",
            "game_num": None, "duration_min": None,
        })
    return {"day_type": "standard", "cards": _attach_keep_going_labels(_apply_guardrails(cards), wt_kg_for_labels)}


def day_layout_v2_enabled() -> bool:
    return os.environ.get("DAY_LAYOUT_V2", "false").lower() == "true"


# Map our card "card" kind -> the existing template_windows "category" vocabulary
# build_today_view + fuel_gauge already understand. Event markers become nudge-only
# (visible, non-tappable). keep_going is shown as a real card (oz/packets).
_CARD_TO_CATEGORY = {
    "everyday_meal": "everyday", "breakfast": "everyday", "lunch": "everyday", "dinner": "everyday",
    "fuel_before": "fuel_before", "top_up": "quick_snack",
    "keep_going": "keep_going", "event": "event",
    "recharge": "fuel_after", "rebuild": "fuel_after", "wind_down": "everyday",
}

# Card kind -> macro-focus label. Labels MUST exist in today_service._FOCUS_MACRO_PCT
# so the downstream per-window gram lookup resolves (empty string for the event marker).
_CARD_TO_MACRO_FOCUS = {
    "everyday_meal": "Balanced Fuel", "breakfast": "Balanced Fuel",
    "lunch": "Balanced Fuel", "dinner": "Balanced Fuel", "wind_down": "Balanced Fuel",
    "fuel_before": "High Carbs", "top_up": "Fast Carbs", "keep_going": "Fast Carbs",
    "recharge": "Recovery Focus", "rebuild": "High Protein + Carbs", "event": "",
}


def cards_to_template_windows(cards: list, date_str: str | None = None) -> list:
    """Adapt day_layout cards to the template_windows shape build_today_view consumes.

    When date_str (YYYY-MM-DD) is provided, open_dt is built from date + card sort_time
    and close_dt = open_dt + 60 min. Without date_str, both stay None (safe — the mobile
    treats empty timing as always-open).
    """
    from datetime import datetime, timedelta
    from api.services.window_templates import _CAT_DISPLAY

    def _to_dt(hhmm: str):
        if not date_str or not hhmm:
            return None
        return datetime.strptime(f"{date_str} {hhmm}", "%Y-%m-%d %H:%M")

    out = []
    for c in cards:
        category = _CARD_TO_CATEGORY.get(c["card"], "everyday")
        # category_key is the semantic carb|hydrate|balanced|recovery vocabulary
        # window_load.py and idea_catalog.IDEAS's fallback section expect — the
        # SAME canonical mapping the legacy engine's _make_window() already uses
        # (window_templates._CAT_DISPLAY), not a second, independently-maintained
        # one. category itself (fuel_before/quick_snack/...) stays a separate
        # field — idea_catalog.IDEAS looks that up first, category_key second.
        category_key = _CAT_DISPLAY.get(category, {}).get("key", category)
        is_nudge = bool(c["is_event"]) or c["card"] == "keep_going"
        macro_focus = (c.get("athlete_label") or "") if c["card"] == "keep_going" \
                      else _CARD_TO_MACRO_FOCUS.get(c["card"], "")
        out.append({
            "key": c["key"],
            "label": c["label"],
            "category": category,
            "category_key": category_key,
            "macro_focus": macro_focus,
            "sort_time": c["sort_time"],
            "time_display": c.get("time_display", ""),
            "open_dt":  _to_dt(c["sort_time"]),
            "close_dt": (_to_dt(c["sort_time"]) + timedelta(minutes=60)) if (date_str and c["sort_time"]) else None,
            "is_nudge_only": is_nudge,
        })
    return out
