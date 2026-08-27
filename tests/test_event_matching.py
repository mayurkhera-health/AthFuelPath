"""Unit tests for the shared event-equivalence matcher (api/services/event_matching.py),
used by both the connected-calendar sync (ics_sync.py) and the direct
event-create endpoint (routes/events.py). See tests/test_ics_sync.py and
tests/test_events_route.py for the integration-level coverage of each caller;
this file is the pure name-comparison logic in isolation.
"""

from api.services.event_matching import normalize_event_name, names_equivalent, find_equivalent_event


def test_normalize_lowercases_trims_and_collapses_whitespace():
    assert normalize_event_name("  Team   Practice  ") == "team practice"
    assert normalize_event_name("TEAM PRACTICE") == "team practice"
    assert normalize_event_name(None) == ""
    assert normalize_event_name("") == ""


def test_names_equivalent_exact_match():
    assert names_equivalent("Team Practice", "Team Practice")
    assert names_equivalent("Team Practice", "team practice"), "case must not matter"
    assert names_equivalent("  Team  Practice ", "Team Practice"), "whitespace must not matter"


def test_names_equivalent_tolerates_trailing_facility_suffix():
    """The confirmed production bug: BYGA appends a court/facility number."""
    assert names_equivalent(
        "Practice: Twin Creeks Sports Complex",
        "Practice: Twin Creeks Sports Complex #10",
    )


def test_names_equivalent_tolerates_facility_suffix_inside_parens():
    """The EXACT real production strings (athlete 71 / Kabir): the facility
    number lands INSIDE a closing paren, not appended after the whole
    string — a pure trailing-prefix comparison alone misses this; it needs
    the substring-level noise-stripping in normalize_event_name()."""
    assert names_equivalent(
        "Practice: U19/18 ECNL & RL Pool (Twin Creeks Sports Complex)",
        "Practice: U19/18 ECNL & RL Pool (Twin Creeks Sports Complex #10)",
    )


def test_names_equivalent_tolerates_trailing_division_code():
    """The confirmed production bug: BYGA appended a division code mid-season."""
    assert names_equivalent(
        "U19/18 ECNL at Marin FC",
        "U19/18 ECNL at Marin FC ECNL G2008/09",
    )


def test_names_equivalent_tolerates_trailing_org_abbreviation():
    """The confirmed production bug: 'San Juan' -> 'San Juan SC'."""
    assert names_equivalent("U19/18 ECNL vs San Juan", "U19/18 ECNL vs San Juan SC")


def test_names_equivalent_is_symmetric():
    a, b = "Practice: Complex", "Practice: Complex #10"
    assert names_equivalent(a, b) == names_equivalent(b, a)


def test_names_equivalent_rejects_different_events():
    """Two genuinely different opponents must never be treated as the same
    event just because they're the same length or share a prefix word."""
    assert not names_equivalent("Soccer vs Team Alpha", "Soccer vs Team Beta")
    assert not names_equivalent("Game vs River City", "Game vs Lakeside")


def test_names_equivalent_rejects_unrelated_short_names():
    assert not names_equivalent("Practice", "Game")
    assert not names_equivalent("Rest Day", "Recovery")


def test_names_equivalent_rejects_empty_or_missing_names():
    assert not names_equivalent("", "Team Practice")
    assert not names_equivalent(None, "Team Practice")
    assert not names_equivalent("", "")


def test_names_equivalent_does_not_truncate_from_the_middle():
    """A suffix match must never let an unrelated LONGER name with a
    different middle word pass as equivalent — only pure trailing growth
    (identical leading words) counts."""
    assert not names_equivalent("Practice at Field A", "Practice at Field B Extra")


def test_find_equivalent_event_fails_closed_on_ambiguous_matches(monkeypatch):
    """More than one candidate row -> None, never guessed at. Exercised at
    the SQL-integration level in test_ics_sync.py's
    test_name_time_fallback_skips_ambiguous_duplicates; this proves the
    guard is really in find_equivalent_event itself via a stubbed conn."""

    class _FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _FakeConn:
        def execute(self, *_args, **_kwargs):
            return _FakeCursor([
                {"id": 1, "event_name": "Team Practice"},
                {"id": 2, "event_name": "Team Practice"},
            ])

    result = find_equivalent_event(
        _FakeConn(), athlete_id=1, event_date="2026-08-26", start_time="19:30",
        event_type="practice", event_name="Team Practice",
        source_sql="source = 'manual'",
    )
    assert result is None


def test_find_equivalent_event_returns_none_without_start_time():
    """No start_time -> no match attempt at all (too loose to be safe)."""
    class _FakeConn:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("must not query the database when start_time is missing")

    result = find_equivalent_event(
        _FakeConn(), athlete_id=1, event_date="2026-08-26", start_time=None,
        event_type="practice", event_name="Team Practice",
        source_sql="source = 'manual'",
    )
    assert result is None
