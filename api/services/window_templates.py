"""
Window Templates Engine — SINGLE source of truth for all fuel window generation.
Both the Today tab and Meal Plan tab read from this engine.
Never duplicate this logic elsewhere.

Spec: FUELUP_WINDOW_TEMPLATES_SPEC.md
"""
from datetime import datetime, date, time, timedelta

# ── SECTION 1: CATEGORIES ─────────────────────────────────────────────────────

CATEGORIES = {
    "fuel_before": {
        "label":          "Fuel Before",
        "nutrient_focus": "Carbs, easy to digest",
        "description":    "Main pre-event meal + top-up snack (folded in)",
        "color_key":      "carb",
    },
    "fuel_during": {
        "label":          "Fuel During",
        "nutrient_focus": "Fast carbs + fluid",
        "description":    "Halftime / between-games. NUDGE ONLY — no tap.",
        "color_key":      "hydrate",
        "tap":            False,
    },
    "fuel_after": {
        "label":          "Fuel After",
        "nutrient_focus": "Protein (repair) + carbs (refill)",
        "description":    "Recovery meal — priority window (first 30 min after)",
        "color_key":      "recovery",
    },
    "everyday": {
        "label":          "Everyday Meal",
        "nutrient_focus": "Balanced; daily iron/calcium/hydration",
        "description":    "Meals not tied to an event",
        "color_key":      "balanced",
    },
    "quick_snack": {
        "label":          "Quick Morning Snack",
        "nutrient_focus": "Light/fast carb",
        "description":    "Early-game substitute for pre-event meal",
        "color_key":      "carb",
    },
    "between_games": {
        "label":          "Between Games Fuel",
        "nutrient_focus": "Carbs + protein + fluid",
        "description":    "Merged recovery/pre-load when gap < 3h",
        "color_key":      "recovery",
    },
    "between_sessions": {
        "label":          "Recovery + Pre-Session Fuel",
        "nutrient_focus": "Carbs + protein + fluid",
        "description":    "Merged recovery/pre-load when gap < 3h30m (training)",
        "color_key":      "recovery",
    },
}

# ── SECTION 3: EARLY-MORNING RULE ─────────────────────────────────────────────

EARLY_MORNING_CUTOFF = time(6, 30)
EARLY_MORNING_MESSAGE = (
    "Early game today! There's no time for a big meal before. "
    "Have a light snack now (like a banana or toast), then eat a "
    "proper breakfast right after you play. Pro athletes do this too."
)

# ── SECTION 4: TOURNAMENT / DOUBLE-SESSION THRESHOLDS ─────────────────────────

MERGED_GAP_THRESHOLD = timedelta(hours=3)          # tournament: gap < 3h → merge
DOUBLE_GAP_THRESHOLD = timedelta(hours=3, minutes=30)  # double-session: 1h–3h30m tier → one merged refuel card
MAX_TAPS_PER_DAY = 5

# ── SECTION 9: TAP QUESTIONS ──────────────────────────────────────────────────

TAP_QUESTIONS = {
    "game":                "Did you fuel before the game?",
    "practice":            "Did you fuel before practice?",
    "strength":            "Fueled before your session?",
    "tournament":          "Did you fuel before game {n}?",
    "game_recovery":       "Did you eat or drink within 30 min after?",
    "practice_recovery":   "Did you have something after practice?",
    "tournament_recovery": "Recovered after game {n}?",
    "between_games":       "Did you eat and drink between games?",
    "between_sessions":    "Did you eat and drink between sessions?",
    "breakfast":           "Did you have breakfast?",
    "lunch":               "Did you eat lunch?",
    "snack":               "Had a snack this afternoon?",
    "dinner":              "Did you have dinner?",
    "quick_snack":         "Had a light snack before the early game?",
    "proper_breakfast":    "Had a proper breakfast after?",
}

# ── SECTION 6: DAY TYPE DISPLAY ───────────────────────────────────────────────

DAY_TYPE_DISPLAY = {
    "rest": {
        "windows":     ["everyday_breakfast", "everyday_lunch", "everyday_snack", "everyday_dinner"],
        "fuel_during": False,
        "description": "Everyday Meals only — recovery day fueling",
    },
    "evening_event": {
        "windows":     ["everyday_breakfast", "everyday_lunch", "pre_event_meal",
                        "fuel_after_primary", "fuel_after_second"],
        "fuel_during": True,
        "note":        "Top-up snack folded into pre_event_meal card",
    },
    "afternoon_game": {
        "windows":     ["everyday_breakfast", "pre_event_meal",
                        "fuel_after_primary", "fuel_after_second", "everyday_dinner"],
        "fuel_during": True,
    },
    "morning_game": {
        "windows":     ["pre_event_meal", "fuel_after_primary", "fuel_after_second",
                        "everyday_lunch", "everyday_dinner"],
        "fuel_during": True,
    },
    "early_game": {
        "windows":     ["quick_morning_snack", "proper_breakfast_after",
                        "fuel_after_primary", "everyday_lunch", "everyday_dinner"],
        "fuel_during":          True,
        "show_teaching_message": True,
    },
    "practice_evening": {
        "windows":     ["everyday_breakfast", "everyday_lunch", "pre_event_meal",
                        "fuel_after_primary", "fuel_after_second"],
        "fuel_during": False,
    },
    "practice_morning": {
        "windows":     ["pre_event_meal", "fuel_after_primary",
                        "everyday_lunch", "everyday_dinner"],
        "fuel_during": False,
    },
    "double_training": {
        "windows":     "computed",
        "fuel_during": False,
        "note":        "Merged or separate depending on gap threshold (3h30m spec tier)",
    },
    "tournament": {
        "windows":     "computed",
        "fuel_during": True,
        "note":        "Merged or separate depending on gap threshold (3h)",
    },
}

# ── CATEGORY → DISPLAY MAPPING ────────────────────────────────────────────────

_CAT_DISPLAY = {
    "fuel_before":  {"key": "carb",     "label": "Build on carbs",  "why": "Carbs before your session keep your legs fresh and your focus sharp."},
    "fuel_during":  {"key": "hydrate",  "label": "Stay hydrated",   "why": "Staying ahead of thirst helps maintain output and reduces cramping."},
    "fuel_after":   {"key": "recovery", "label": "Recovery fuel",   "why": "Within 30 min of finishing, protein + carbs kick-start muscle repair."},
    "everyday":     {"key": "balanced", "label": "Fuel + rebuild",  "why": "A balanced mix of carbs, protein, and healthy fats sets a solid base."},
    "quick_snack":  {"key": "carb",     "label": "Build on carbs",  "why": "A light carb snack keeps your energy up before an early session."},
    "between_games":   {"key": "recovery", "label": "Recovery fuel", "why": "Between games: recover from the last and fuel up for the next."},
    "between_sessions":{"key": "recovery", "label": "Recovery fuel", "why": "Recover from your first session and load up carbs + protein before the next one."},
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def _parse_hhmm(hhmm: str) -> time:
    # Normalise: strip whitespace, upper-case, collapse spaces so
    # "3:30pm", "3:30 pm", "3:30 PM" all become "3:30PM".
    s = hhmm.strip().upper().replace(" ", "")
    for fmt in ("%H:%M", "%I:%M%p"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse time string: {hhmm!r}")


def _fmt12(dt: datetime) -> str:
    """datetime → '7:30 AM'"""
    h = dt.hour % 12 or 12
    period = "AM" if dt.hour < 12 else "PM"
    if dt.minute:
        return f"{h}:{dt.minute:02d} {period}"
    return f"{h}:00 {period}"


def _fmt_range(open_dt: datetime, close_dt: datetime) -> str:
    return f"{_fmt12(open_dt)} – {_fmt12(close_dt)}"


def _sort_key(open_dt: datetime) -> str:
    return f"{open_dt.hour:02d}:{open_dt.minute:02d}"


# ── SECTION 5: GUARDRAIL HELPERS ─────────────────────────────────────────────

def clamp_window_open(open_dt: datetime) -> datetime:
    """GUARDRAIL 1: Never show a window open time before 06:30."""
    if open_dt.time() < EARLY_MORNING_CUTOFF:
        return open_dt.replace(hour=6, minute=30, second=0, microsecond=0)
    return open_dt


def between_games_viable(open_dt: datetime, close_dt: datetime) -> bool:
    """GUARDRAIL 2: Between-games window must be at least 20 min wide."""
    return (close_dt - open_dt) >= timedelta(minutes=20)


# ── SECTION 3: EARLY-MORNING RULE ─────────────────────────────────────────────

def apply_early_morning_rule(E_start: datetime) -> bool:
    """Returns True if the Pre-Event Meal window would open before 06:30."""
    pre_event_open = E_start - timedelta(hours=3)
    return pre_event_open.time() < EARLY_MORNING_CUTOFF


# ── WINDOW BUILDERS ───────────────────────────────────────────────────────────

def _make_window(
    key: str,
    label: str,
    category: str,
    open_dt: datetime,
    close_dt: datetime,
    tap: bool = True,
    tap_label: str = "",
    priority: bool = False,
    is_nudge_only: bool = False,
    note: str = "",
    early_morning_message: str | None = None,
) -> dict:
    cat = CATEGORIES[category]
    disp = _CAT_DISPLAY[category]
    return {
        "key":                   key,
        "slot_name":             key,
        "label":                 label,
        "display_label":         label,
        "category":              category,
        "category_key":          disp["key"],
        "category_label":        cat["label"],
        "why":                   disp["why"],
        "open_dt":               open_dt,
        "close_dt":              close_dt,
        "eat_by_time":           _fmt_range(open_dt, close_dt),
        "time_display":          _fmt_range(open_dt, close_dt),
        "sort_time":             _sort_key(open_dt),
        "tap":                   tap,
        "tap_label":             tap_label,
        "priority":              priority,
        "is_nudge_only":         is_nudge_only,
        "is_hydration":          is_nudge_only,
        "note":                  note,
        "early_morning_message": early_morning_message,
    }


def _everyday_breakfast(base_date: date) -> dict:
    open_dt  = datetime.combine(base_date, time(7, 0))
    close_dt = datetime.combine(base_date, time(9, 0))
    return _make_window("everyday_breakfast", "Breakfast", "everyday",
                        open_dt, close_dt, tap_label=TAP_QUESTIONS["breakfast"])


def _everyday_lunch(base_date: date) -> dict:
    open_dt  = datetime.combine(base_date, time(12, 0))
    close_dt = datetime.combine(base_date, time(13, 30))
    return _make_window("everyday_lunch", "Lunch", "everyday",
                        open_dt, close_dt, tap_label=TAP_QUESTIONS["lunch"])


def _everyday_snack(base_date: date) -> dict:
    open_dt  = datetime.combine(base_date, time(15, 0))
    close_dt = datetime.combine(base_date, time(16, 30))
    return _make_window("everyday_snack", "Afternoon Snack", "everyday",
                        open_dt, close_dt, tap_label=TAP_QUESTIONS["snack"])


def _everyday_dinner(base_date: date) -> dict:
    open_dt  = datetime.combine(base_date, time(18, 30))
    close_dt = datetime.combine(base_date, time(20, 0))
    return _make_window("everyday_dinner", "Dinner", "everyday",
                        open_dt, close_dt, tap_label=TAP_QUESTIONS["dinner"])


def _pre_event_meal(E_start: datetime, event_norm: str = "game", suffix: str = "") -> dict:
    open_dt  = clamp_window_open(E_start - timedelta(hours=3))
    close_dt = E_start - timedelta(hours=2, minutes=45)
    if close_dt <= open_dt:
        close_dt = open_dt + timedelta(minutes=30)
    key = f"pre_event_meal{suffix}"
    q_key = "tournament" if "tournament" in event_norm else "game" if "game" in event_norm else "practice"
    return _make_window(
        key, "Pre-Event Meal", "fuel_before", open_dt, close_dt,
        tap_label=TAP_QUESTIONS.get(q_key, TAP_QUESTIONS["game"]),
        note="Also aim for a light snack 30–60 min before if you can.",
    )


def _quick_morning_snack(E_start: datetime) -> dict:
    open_dt  = clamp_window_open(E_start - timedelta(minutes=60))
    close_dt = E_start - timedelta(minutes=30)
    if close_dt <= open_dt:
        close_dt = open_dt + timedelta(minutes=15)
    return _make_window(
        "quick_morning_snack", "Quick Morning Snack", "quick_snack", open_dt, close_dt,
        tap_label=TAP_QUESTIONS["quick_snack"],
        early_morning_message=EARLY_MORNING_MESSAGE,
    )


def _proper_breakfast_after(E_end: datetime, suffix: str = "") -> dict:
    open_dt  = E_end
    close_dt = E_end + timedelta(hours=1)
    key = f"proper_breakfast_after{suffix}"
    return _make_window(key, "Proper Breakfast", "fuel_after",
                        open_dt, close_dt, tap_label=TAP_QUESTIONS["proper_breakfast"])


def _fuel_after_primary(E_end: datetime, event_norm: str = "game", suffix: str = "") -> dict:
    open_dt  = E_end
    close_dt = E_end + timedelta(minutes=30)
    key = f"fuel_after_primary{suffix}"
    q_key = ("tournament_recovery" if "tournament" in event_norm
              else "game_recovery" if "game" in event_norm
              else "practice_recovery")
    return _make_window(key, "Recovery Window", "fuel_after",
                        open_dt, close_dt, tap_label=TAP_QUESTIONS[q_key], priority=True)


def _fuel_after_second(E_end: datetime, event_norm: str = "game", suffix: str = "") -> dict:
    open_dt  = E_end + timedelta(hours=1)
    close_dt = E_end + timedelta(hours=2)
    key = f"fuel_after_second{suffix}"
    q_key = ("tournament_recovery" if "tournament" in event_norm
              else "game_recovery" if "game" in event_norm
              else "practice_recovery")
    return _make_window(key, "Recovery Meal", "fuel_after",
                        open_dt, close_dt, tap_label=TAP_QUESTIONS[q_key])


def _fuel_during_nudge(E_start: datetime, E_end: datetime) -> dict:
    midpoint = E_start + (E_end - E_start) / 2
    open_dt  = midpoint - timedelta(minutes=5)
    close_dt = midpoint + timedelta(minutes=5)
    return _make_window(
        "fuel_during_nudge", "Halftime Fuel Nudge", "fuel_during",
        open_dt, close_dt, tap=False, is_nudge_only=True,
    )


# ── SECTION 6: DAY TYPE DETERMINATION ────────────────────────────────────────

def determine_day_type(events: list, date_str: str) -> str:
    """Classify a day into one of 9 day types based on its events."""
    if not events:
        return "rest"

    def _norm(e): return e.get("event_type", "").lower()

    def _is_game(e): return "game" in _norm(e) or "tournament" in _norm(e)
    def _is_practice(e): return any(x in _norm(e) for x in ("practice", "training", "strength", "conditioning", "agility"))

    game_events     = [e for e in events if _is_game(e)]
    practice_events = [e for e in events if _is_practice(e)]

    if len(game_events) >= 2 or any("tournament" in _norm(e) for e in events):
        return "tournament"

    if len(game_events) == 0 and len(practice_events) >= 2:
        return "double_training"

    if game_events:
        ev = game_events[0]
        start_str = ev.get("start_time")
        if not start_str:
            return "rest"
        base = date.fromisoformat(date_str)
        E_start = datetime.combine(base, _parse_hhmm(start_str))
        if apply_early_morning_rule(E_start):
            return "early_game"
        h = E_start.hour + E_start.minute / 60
        if h < 12:
            return "morning_game"
        if h < 17:
            return "afternoon_game"
        return "evening_event"

    if practice_events:
        ev = practice_events[0]
        start_str = ev.get("start_time")
        if not start_str:
            return "rest"
        base = date.fromisoformat(date_str)
        E_start = datetime.combine(base, _parse_hhmm(start_str))
        h = E_start.hour + E_start.minute / 60
        return "practice_evening" if h >= 17 else "practice_morning"

    return "rest"


# ── SECTION 4: TOURNAMENT / DOUBLE-SESSION BUILDERS ──────────────────────────

def build_tournament_windows(games: list, base_date: date) -> tuple:
    """
    games: list of event dicts sorted by start_time ascending.
    Returns (windows, early_morning_message | None).
    """
    windows   = []
    early_msg = None
    n         = len(games)

    for i, game in enumerate(games):
        start_str = game.get("start_time")
        dur       = game.get("duration_hours") or 1.5
        event_norm = game.get("event_type", "game").lower()
        if not start_str:
            continue
        E_start = datetime.combine(base_date, _parse_hhmm(start_str))
        E_end   = E_start + timedelta(hours=dur)

        # PRE-EVENT (first game, or handled after gap >= 3h)
        if i == 0:
            if apply_early_morning_rule(E_start):
                early_msg = EARLY_MORNING_MESSAGE
                windows.append(_quick_morning_snack(E_start))
            else:
                windows.append(_pre_event_meal(E_start, event_norm, suffix=f"_{i+1}"))

        # FUEL DURING — nudge only, every game
        windows.append(_fuel_during_nudge(E_start, E_end))

        if i < n - 1:
            next_game     = games[i + 1]
            next_start_str = next_game.get("start_time")
            if not next_start_str:
                continue
            next_E_start = datetime.combine(base_date, _parse_hhmm(next_start_str))
            gap = next_E_start - E_end

            if gap < MERGED_GAP_THRESHOLD:
                # Gap < 3h → ONE merged between-games window
                bg_open  = clamp_window_open(E_end + timedelta(minutes=20))
                bg_close = next_E_start - timedelta(minutes=45)
                key      = f"between_games_{i+1}_{i+2}"
                if between_games_viable(bg_open, bg_close):
                    windows.append(_make_window(
                        key, f"Between Games {i+1} & {i+2}", "between_games",
                        bg_open, bg_close,
                        tap_label=TAP_QUESTIONS["between_games"],
                        priority=True,
                        note="Both recovery from last game and fuel for next.",
                    ))
                else:
                    windows.append(_make_window(
                        key, f"Between Games {i+1} & {i+2}", "between_games",
                        E_end, next_E_start, tap=False, is_nudge_only=True,
                        note="Games are back-to-back — grab what you can",
                    ))
            else:
                # Gap >= 3h → separate recovery + pre-event
                windows.append(_fuel_after_primary(E_end, event_norm, suffix=f"_{i+1}"))
                windows.append(_fuel_after_second(E_end, event_norm, suffix=f"_{i+1}"))
                if not apply_early_morning_rule(next_E_start):
                    next_norm = next_game.get("event_type", "game").lower()
                    windows.append(_pre_event_meal(next_E_start, next_norm, suffix=f"_{i+2}"))

        else:
            # Last game
            if early_msg:
                windows.append(_proper_breakfast_after(E_end, suffix="_last"))
            windows.append(_fuel_after_primary(E_end, event_norm, suffix=f"_{i+1}"))
            windows.append(_fuel_after_second(E_end, event_norm, suffix=f"_{i+1}"))

    # GUARDRAIL 5: everyday dinner only if last game ends before 17:30
    if games:
        last = games[-1]
        last_start_str = last.get("start_time")
        last_dur       = last.get("duration_hours") or 1.5
        if last_start_str:
            last_E_end = datetime.combine(base_date, _parse_hhmm(last_start_str)) + timedelta(hours=last_dur)
            if last_E_end.time() < time(17, 30):
                windows.append(_everyday_dinner(base_date))

    return windows, early_msg


def build_double_session_windows(sessions: list, base_date: date) -> tuple:
    """
    sessions: list of training event dicts sorted by start_time.
    Returns (windows, early_morning_message | None).
    """
    windows   = []
    early_msg = None
    n         = len(sessions)

    for i, session in enumerate(sessions):
        start_str  = session.get("start_time")
        dur        = session.get("duration_hours") or 1.5
        event_norm = session.get("event_type", "practice").lower()
        if not start_str:
            continue
        E_start = datetime.combine(base_date, _parse_hhmm(start_str))
        E_end   = E_start + timedelta(hours=dur)

        if i == 0:
            if apply_early_morning_rule(E_start):
                early_msg = EARLY_MORNING_MESSAGE
                windows.append(_quick_morning_snack(E_start))
            else:
                windows.append(_pre_event_meal(E_start, event_norm, suffix=f"_{i+1}"))

        if i < n - 1:
            next_session   = sessions[i + 1]
            next_start_str = next_session.get("start_time")
            if not next_start_str:
                continue
            next_E_start = datetime.combine(base_date, _parse_hhmm(next_start_str))
            gap = next_E_start - E_end

            if gap < DOUBLE_GAP_THRESHOLD:
                bg_open  = clamp_window_open(E_end + timedelta(minutes=20))
                bg_close = next_E_start - timedelta(minutes=30)
                key      = f"between_sessions_{i+1}_{i+2}"
                if between_games_viable(bg_open, bg_close):
                    windows.append(_make_window(
                        key, f"Between Sessions {i+1} & {i+2}", "between_sessions",
                        bg_open, bg_close,
                        tap_label=TAP_QUESTIONS["between_sessions"],
                        priority=True,
                    ))
                else:
                    windows.append(_make_window(
                        key, f"Between Sessions {i+1} & {i+2}", "between_sessions",
                        E_end, next_E_start, tap=False, is_nudge_only=True,
                        note="Sessions are back-to-back — grab what you can",
                    ))
            else:
                windows.append(_fuel_after_primary(E_end, event_norm, suffix=f"_{i+1}"))
                next_norm = next_session.get("event_type", "practice").lower()
                windows.append(_pre_event_meal(next_E_start, next_norm, suffix=f"_{i+2}"))
        else:
            windows.append(_fuel_after_primary(E_end, event_norm, suffix=f"_{i+1}"))

    # Everyday meals that fit around the sessions
    windows.append(_everyday_lunch(base_date))
    windows.append(_everyday_dinner(base_date))

    return windows, early_msg


# ── SINGLE-EVENT DAY BUILDER ─────────────────────────────────────────────────

def _build_rest_day_windows(base_date: date) -> list:
    return [
        _everyday_breakfast(base_date),
        _everyday_lunch(base_date),
        _everyday_snack(base_date),
        _everyday_dinner(base_date),
    ]


def _build_event_day_windows(event: dict, day_type: str, base_date: date) -> tuple:
    """Returns (windows, early_morning_message | None)."""
    start_str  = event.get("start_time")
    dur        = event.get("duration_hours") or 1.5
    event_norm = event.get("event_type", "").lower()
    if not start_str:
        return _build_rest_day_windows(base_date), None

    E_start = datetime.combine(base_date, _parse_hhmm(start_str))
    E_end   = E_start + timedelta(hours=dur)
    is_game = "game" in event_norm or "tournament" in event_norm
    windows = []
    early_msg = None

    if day_type == "early_game":
        early_msg = EARLY_MORNING_MESSAGE
        windows.append(_quick_morning_snack(E_start))
        if is_game:
            windows.append(_fuel_during_nudge(E_start, E_end))
        windows.append(_fuel_after_primary(E_end, event_norm))
        windows.append(_proper_breakfast_after(E_end))
        windows.append(_everyday_lunch(base_date))
        windows.append(_everyday_dinner(base_date))

    elif day_type == "morning_game":
        windows.append(_pre_event_meal(E_start, event_norm))
        if is_game:
            windows.append(_fuel_during_nudge(E_start, E_end))
        windows.append(_fuel_after_primary(E_end, event_norm))
        windows.append(_fuel_after_second(E_end, event_norm))
        windows.append(_everyday_lunch(base_date))
        windows.append(_everyday_dinner(base_date))

    elif day_type == "afternoon_game":
        windows.append(_everyday_breakfast(base_date))
        windows.append(_pre_event_meal(E_start, event_norm))
        if is_game:
            windows.append(_fuel_during_nudge(E_start, E_end))
        windows.append(_fuel_after_primary(E_end, event_norm))
        windows.append(_fuel_after_second(E_end, event_norm))
        # GUARDRAIL 5: dinner only if event ends before 17:30
        if E_end.time() < time(17, 30):
            windows.append(_everyday_dinner(base_date))

    elif day_type == "evening_event":
        windows.append(_everyday_breakfast(base_date))
        windows.append(_everyday_lunch(base_date))
        windows.append(_pre_event_meal(E_start, event_norm))
        if is_game:
            windows.append(_fuel_during_nudge(E_start, E_end))
        windows.append(_fuel_after_primary(E_end, event_norm))
        windows.append(_fuel_after_second(E_end, event_norm))

    elif day_type == "practice_morning":
        windows.append(_pre_event_meal(E_start, event_norm))
        windows.append(_fuel_after_primary(E_end, event_norm))
        windows.append(_everyday_lunch(base_date))
        windows.append(_everyday_dinner(base_date))

    elif day_type == "practice_evening":
        windows.append(_everyday_breakfast(base_date))
        windows.append(_everyday_lunch(base_date))
        windows.append(_pre_event_meal(E_start, event_norm))
        windows.append(_fuel_after_primary(E_end, event_norm))
        windows.append(_fuel_after_second(E_end, event_norm))

    else:
        return _build_rest_day_windows(base_date), None

    return windows, early_msg


# ── SECTION 5: GUARDRAILS ─────────────────────────────────────────────────────

def _apply_guardrails(windows: list) -> list:
    """Apply all 5 guardrails to window list."""

    # GUARDRAIL 1: clamp open times (already applied at creation, but final pass)
    for w in windows:
        if not w.get("is_nudge_only") and w["open_dt"].time() < EARLY_MORNING_CUTOFF:
            w["open_dt"] = w["open_dt"].replace(hour=6, minute=30, second=0, microsecond=0)
            w["eat_by_time"] = _fmt_range(w["open_dt"], w["close_dt"])
            w["time_display"] = w["eat_by_time"]
            w["sort_time"]    = _sort_key(w["open_dt"])

    # GUARDRAIL 3: no stacking within 15 min — drop everyday windows first.
    # If neither window is everyday, keep both (they serve distinct purposes).
    tap_windows = [w for w in windows if not w.get("is_nudge_only")]
    tap_windows.sort(key=lambda w: w["open_dt"])
    to_drop: set = set()
    for i in range(len(tap_windows) - 1):
        a, b = tap_windows[i], tap_windows[i + 1]
        if b["open_dt"] - a["open_dt"] < timedelta(minutes=15):
            if a["category"] == "everyday":
                to_drop.add(a["key"])
            elif b["category"] == "everyday":
                to_drop.add(b["key"])
            # Neither is everyday — distinct windows, keep both
    windows = [w for w in windows if w["key"] not in to_drop]

    # GUARDRAIL 4: max 5 confirmation taps
    tap_windows = [w for w in windows if w.get("tap", True) and not w.get("is_nudge_only")]
    drop_order  = ["everyday_snack", "everyday_lunch", "fuel_after_second",
                   "everyday_breakfast", "everyday_dinner"]
    while len(tap_windows) > MAX_TAPS_PER_DAY:
        dropped = False
        for drop_key in drop_order:
            keys = [w["key"] for w in tap_windows]
            if drop_key in keys:
                windows = [w for w in windows if w["key"] != drop_key]
                dropped = True
                break
            # Handle keyed variants like fuel_after_second_1
            variant = next((k for k in keys if k.startswith(drop_key.replace("fuel_after_second", "fuel_after_second"))), None)
            if variant:
                windows = [w for w in windows if w["key"] != variant]
                dropped = True
                break
        if not dropped:
            break
        tap_windows = [w for w in windows if w.get("tap", True) and not w.get("is_nudge_only")]

    # Sort chronologically
    windows.sort(key=lambda w: w["open_dt"])
    return windows


# ── MAIN ENGINE ───────────────────────────────────────────────────────────────

def generate_windows_for_day(athlete_id: int, date_str: str, events: list, force_v2: bool = False) -> dict:
    """
    Single engine entry point.
    Returns {day_type, early_morning_message, windows[]}.
    windows[] excludes fuel_during nudges — callers filter is_nudge_only for UI.
    """
    # ── Event-relative engine (feature flag or per-request override) ──────────
    try:
        from api.services.window_engine_v2 import (
            generate_windows_v2, event_relative_windows_enabled, Event as V2Event,
        )
        if force_v2 or event_relative_windows_enabled():
            base_date = date.fromisoformat(date_str)
            v2_events = [
                V2Event(
                    id             = int(e.get("id") or 0),
                    athlete_id     = athlete_id,
                    event_type     = e.get("event_type") or "rest",
                    event_date     = date_str,
                    start_time     = e.get("start_time") or "00:00",
                    duration_hours = e.get("duration_hours"),
                )
                for e in events
            ]
            result = generate_windows_v2(v2_events, date_str)
            windows = []
            for w in result.windows:
                oh, om  = int(w.open_time[:2]),  int(w.open_time[3:])
                ch, cm  = int(w.close_time[:2]), int(w.close_time[3:])
                open_dt  = datetime.combine(base_date, time(oh, om))
                close_dt = datetime.combine(base_date, time(ch, cm))
                windows.append({
                    "key":           w.window_key,
                    "slot_name":     w.window_key,
                    "label":         w.label,
                    "display_label": w.label,
                    "category":      w.category,
                    "category_key":  w.category_key,
                    "category_label": w.category_label,
                    "why":           w.why,
                    "open_dt":       open_dt,
                    "close_dt":      close_dt,
                    "eat_by_time":   w.time_display,
                    "time_display":  w.time_display,
                    "sort_time":     w.sort_time,
                    "macro_focus":   w.macro_focus,
                    "tap":           w.is_tappable,
                    "priority":      w.priority,
                    "is_nudge_only": not w.is_tappable,
                    "is_hydration":  not w.is_tappable,
                    "note":          "",
                })
            return {
                "day_type":              result.day_type,
                "early_morning_message": result.early_morning_message,
                "windows":               windows,
            }
    except ImportError:
        pass  # window_engine_v2 not deployed yet — fall through to old engine

    # ── Old clock-based engine ────────────────────────────────────────────────
    base_date = date.fromisoformat(date_str)
    day_type  = determine_day_type(events, date_str)

    if day_type == "tournament":
        def _is_game(e): return "game" in e.get("event_type","").lower() or "tournament" in e.get("event_type","").lower()
        game_events = sorted([e for e in events if _is_game(e)], key=lambda e: e.get("start_time") or "")
        if not game_events:
            game_events = events
        windows, early_msg = build_tournament_windows(game_events, base_date)

    elif day_type == "double_training":
        def _is_practice(e): return any(x in e.get("event_type","").lower() for x in ("practice","training","strength","conditioning","agility"))
        prac_events = sorted([e for e in events if _is_practice(e)], key=lambda e: e.get("start_time") or "")
        if not prac_events:
            prac_events = events
        windows, early_msg = build_double_session_windows(prac_events, base_date)

    elif day_type == "rest":
        windows   = _build_rest_day_windows(base_date)
        early_msg = None

    else:
        def _is_game(e): return "game" in e.get("event_type","").lower() or "tournament" in e.get("event_type","").lower()
        def _is_practice(e): return any(x in e.get("event_type","").lower() for x in ("practice","training","strength","conditioning","agility"))
        if day_type in ("early_game", "morning_game", "afternoon_game", "evening_event"):
            game_events = [e for e in events if _is_game(e)]
            event = game_events[0] if game_events else events[0]
        else:
            prac_events = [e for e in events if _is_practice(e)]
            event = prac_events[0] if prac_events else events[0]
        windows, early_msg = _build_event_day_windows(event, day_type, base_date)

    windows = _apply_guardrails(windows)

    return {
        "day_type":             day_type,
        "early_morning_message": early_msg,
        "windows":              windows,
    }


# ── SECTION 8: AUTO-RECALCULATION TRIGGER ────────────────────────────────────

def on_event_added_or_changed(athlete_id: int, event_date: str, conn) -> dict:
    """
    Fires whenever a new event is created, updated, or deleted.
    Recalculates all windows for that date from scratch.
    Returns the updated engine result dict.
    """
    events = [dict(r) for r in conn.execute(
        "SELECT * FROM events WHERE athlete_id = ? AND event_date = ? ORDER BY start_time",
        (athlete_id, event_date),
    ).fetchall()]
    return generate_windows_for_day(athlete_id, event_date, events)


def scheduled_tap_window_keys(athlete_id: int, date_str: str, conn) -> list[str]:
    """Window keys the engine would show as confirmable ("tap") for this
    athlete on this day — the real, variable per-day denominator for
    completion scoring. Mirrors on_event_added_or_changed's event fetch;
    this is the single source of truth for "how many windows were actually
    scheduled" (1-5 per the guardrails, never a fixed constant)."""
    events = [dict(r) for r in conn.execute(
        "SELECT * FROM events WHERE athlete_id = ? AND event_date = ? ORDER BY start_time",
        (athlete_id, date_str),
    ).fetchall()]
    result = generate_windows_for_day(athlete_id, date_str, events)
    return [w["key"] for w in result["windows"] if w.get("tap", True)]
