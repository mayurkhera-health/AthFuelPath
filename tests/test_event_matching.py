"""Unit tests for the shared event-equivalence matcher (api/services/event_matching.py),
used by both the connected-calendar sync (ics_sync.py) and the direct
event-create endpoint (routes/events.py). See tests/test_ics_sync.py and
tests/test_events_route.py for the integration-level coverage of each caller;
this file is the pure name-comparison logic in isolation.
"""

from api.services.event_matching import (
    normalize_event_name, names_equivalent, find_equivalent_event, materially_conflicts, MatchStatus,
)


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


def test_names_equivalent_tolerates_ecnl_rl_marker_format_drift():
    """Confirmed production bug (Nora / athlete 62): BYGA represents the same
    ECNL/RL competition marker in different textual forms across exports —
    a parenthesized "(ECNL-RL)" suffix in one export, a spaced-out
    "ECNL RL" plus the already-tolerated trailing division code in another.
    Same logical game, must be recognized as equivalent."""
    assert names_equivalent(
        "U13 ECNL & RL Girls at Marin FC (ECNL-RL)",
        "U13 ECNL & RL Girls at Marin FC ECNL RL G2013/14",
    )


def test_names_equivalent_ecnl_rl_marker_symmetric():
    a = "U13 ECNL & RL Girls at Marin FC (ECNL-RL)"
    b = "U13 ECNL & RL Girls at Marin FC ECNL RL G2013/14"
    assert names_equivalent(a, b) == names_equivalent(b, a)


def test_names_equivalent_tolerates_ecnl_rl_hyphenated_form():
    """The plain hyphenated form (no parens) must also be recognized as the
    same marker as the spaced-out form."""
    assert names_equivalent(
        "U15 RL Girls at Marin FC ECNL-RL",
        "U15 RL Girls at Marin FC ECNL RL G2011/12",
    )


# ─── ECNL-RL marker: required false-positive protection ────────────────────
# The new tolerance must ONLY recognize the combined ECNL+RL marker in one of
# its observed forms — it must never let a bare "ECNL" or bare "RL" side
# collapse into an "ECNL-RL" side, and must never affect any other name pair.

def test_names_equivalent_rejects_ecnl_vs_rl():
    assert not names_equivalent("U13 Girls at Marin FC ECNL", "U13 Girls at Marin FC RL")


def test_names_equivalent_rejects_ecnl_vs_ecnl_rl():
    assert not names_equivalent(
        "U13 Girls at Marin FC ECNL", "U13 Girls at Marin FC (ECNL-RL)",
    )
    assert not names_equivalent(
        "U13 Girls at Marin FC ECNL", "U13 Girls at Marin FC ECNL-RL",
    )


def test_names_equivalent_rejects_rl_vs_ecnl_rl():
    assert not names_equivalent(
        "U13 Girls at Marin FC RL", "U13 Girls at Marin FC (ECNL-RL)",
    )


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


# ─── False-positive protection: the matcher is NOT "one name starts with
# the other" — reviewed and deliberately rejected as too permissive. Only an
# exact match, a stripped noise token, or ONE extra trailing word from the
# explicit _TRAILING_ORG_MARKERS allowlist counts as equivalent. Everything
# below must stay DIFFERENT. ────────────────────────────────────────────────

def test_names_equivalent_rejects_same_length_game_numbers():
    assert not names_equivalent("U15 Game 1", "U15 Game 2")


def test_names_equivalent_rejects_same_length_team_colors():
    assert not names_equivalent("San Juan SC Blue", "San Juan SC White")


def test_names_equivalent_rejects_same_length_field_numbers():
    assert not names_equivalent("Training Field 1", "Training Field 2")


def test_names_equivalent_rejects_trailing_word_not_on_allowlist():
    """A REAL prior bug this matcher had: a plain 'one starts with the
    other' check would wrongly match every one of these — a genuinely
    different session/team/makeup qualifier is not provider noise."""
    assert not names_equivalent("Practice", "Practice Advanced")
    assert not names_equivalent("U15 Game", "U15 Game Makeup")
    assert not names_equivalent("Team A", "Team A JV")
    assert not names_equivalent("Practice: Field House", "Practice: Field House B")


def test_names_equivalent_rejects_two_extra_trailing_words():
    """Even when the final word IS on the allowlist, more than one extra
    trailing word is too much drift to call it noise."""
    assert not names_equivalent("San Juan", "San Juan Rec SC")


def test_names_equivalent_rejects_distinct_events_same_date_time_type():
    """Two different clubs/events that happen to land on the same
    athlete/date/time/type must never be merged by name comparison alone —
    this is exactly what find_equivalent_event's caller-supplied athlete_id
    + event_date + start_time + event_type filter is for; name comparison
    on its own must stay conservative on top of that."""
    assert not names_equivalent("Marin FC Practice", "Davis Legacy Practice")


def test_find_equivalent_event_distinguishes_ambiguous_from_no_match():
    """The core Issue-2 fix: AMBIGUOUS_MATCH and NO_MATCH are different
    statuses, not both collapsed into a falsy None — a caller MUST be able
    to tell "duplicates already exist here, don't add another" apart from
    "genuinely nothing here, safe to insert". Exercised at the
    SQL-integration level in test_ics_sync.py/test_events_route.py; this
    proves the distinction is real in find_equivalent_event itself via a
    stubbed conn."""

    class _FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _AmbiguousConn:
        def execute(self, *_args, **_kwargs):
            return _FakeCursor([
                {"id": 1, "event_name": "Team Practice"},
                {"id": 2, "event_name": "Team Practice"},
            ])

    ambiguous = find_equivalent_event(
        _AmbiguousConn(), athlete_id=1, event_date="2026-08-26", start_time="19:30",
        event_type="practice", event_name="Team Practice",
        source_sql="source = 'manual'",
    )
    assert ambiguous.status == MatchStatus.AMBIGUOUS_MATCH
    assert ambiguous.row is None, "ambiguous must never arbitrarily pick a row"
    assert ambiguous.candidate_count == 2

    class _EmptyConn:
        def execute(self, *_args, **_kwargs):
            return _FakeCursor([])

    no_match = find_equivalent_event(
        _EmptyConn(), athlete_id=1, event_date="2026-08-26", start_time="19:30",
        event_type="practice", event_name="Team Practice",
        source_sql="source = 'manual'",
    )
    assert no_match.status == MatchStatus.NO_MATCH
    assert no_match.row is None
    assert no_match.candidate_count == 0
    assert no_match.status != ambiguous.status, \
        "NO_MATCH and AMBIGUOUS_MATCH must be distinguishable statuses"


def test_find_equivalent_event_exactly_one_match_returns_the_row():
    class _FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _OneMatchConn:
        def execute(self, *_args, **_kwargs):
            return _FakeCursor([{"id": 7, "event_name": "Team Practice"}])

    result = find_equivalent_event(
        _OneMatchConn(), athlete_id=1, event_date="2026-08-26", start_time="19:30",
        event_type="practice", event_name="Team Practice",
        source_sql="source = 'manual'",
    )
    assert result.status == MatchStatus.EXACTLY_ONE_MATCH
    assert result.row == {"id": 7, "event_name": "Team Practice"}
    assert result.candidate_count == 1


def test_find_equivalent_event_returns_no_match_without_start_time():
    """No start_time -> no match attempt at all (too loose to be safe)."""
    class _FakeConn:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("must not query the database when start_time is missing")

    result = find_equivalent_event(
        _FakeConn(), athlete_id=1, event_date="2026-08-26", start_time=None,
        event_type="practice", event_name="Team Practice",
        source_sql="source = 'manual'",
    )
    assert result.status == MatchStatus.NO_MATCH
    assert result.row is None


# ─── Pair-aware facility-number / division-code conflicts (Issues 1-3) ─────
# Independently stripping a facility number or division code from BOTH sides
# before comparing was a real bug this module had: "Complex #10" and
# "Complex #11" both strip to "Complex" and would wrongly compare equal.
# The fix compares the extracted VALUES pairwise — two present-and-different
# values is always a real difference, never tolerated.

def test_conflicting_facility_numbers_stay_distinct():
    assert not names_equivalent("Practice: Complex #10", "Practice: Complex #11")
    assert not names_equivalent("Field #1", "Field #2")
    assert not names_equivalent("Court #1", "Court #2")
    assert not names_equivalent("Arena #1", "Arena #2")


def test_missing_vs_present_facility_number_still_tolerated():
    """One side with no number, one with a number in the recognized venue
    context -> still the original provider-noise tolerance."""
    assert names_equivalent("Practice: Complex", "Practice: Complex #10")


def test_same_facility_number_both_sides_matches():
    assert names_equivalent("Practice: Complex #10", "Practice: Complex #10")


def test_conflicting_division_codes_stay_distinct():
    assert not names_equivalent(
        "U19/18 ECNL at Marin FC ECNL G2008/09",
        "U19/18 ECNL at Marin FC ECNL G2009/10",
    )


def test_missing_vs_present_division_code_still_tolerated():
    assert names_equivalent(
        "U19/18 ECNL at Marin FC", "U19/18 ECNL at Marin FC ECNL G2008/09",
    )


def test_parenthesized_non_venue_numbers_stay_distinct():
    """A parenthesized segment is NOT automatically a venue — only an
    explicit venue keyword immediately before the number counts."""
    assert not names_equivalent("Tournament (Game #1)", "Tournament (Game #2)")
    assert not names_equivalent("Session (Group #1)", "Session (Group #2)")


def test_real_twin_creeks_parenthesized_venue_case_still_matches():
    assert names_equivalent(
        "Practice: U19/18 ECNL & RL Pool (Twin Creeks Sports Complex)",
        "Practice: U19/18 ECNL & RL Pool (Twin Creeks Sports Complex #10)",
    )


# ─── Material-field conflict guard (Issue 4) ────────────────────────────────

def test_materially_conflicts_missing_venue_on_one_side_dedupes():
    """An imported duplicate with venue info missing on one side must still
    dedupe — missing data is never treated as a conflict."""
    existing = {"duration_hours": 1.5, "venue_name": None, "city": None, "address": None}
    candidate = {"duration_hours": 1.5, "venue_name": "Twin Creeks Sports Complex",
                 "city": None, "address": None}
    assert not materially_conflicts(existing, candidate)
    assert not materially_conflicts(candidate, existing)


def test_materially_conflicts_same_venue_both_sides_dedupes():
    existing = {"duration_hours": 1.5, "venue_name": "Twin Creeks Sports Complex",
                "city": "San Jose", "address": None}
    candidate = {"duration_hours": 1.5, "venue_name": "Twin Creeks Sports Complex",
                 "city": "San Jose", "address": None}
    assert not materially_conflicts(existing, candidate)


def test_materially_conflicts_clearly_different_venue_blocks_adoption():
    existing = {"duration_hours": 1.5, "venue_name": "Twin Creeks Sports Complex",
                "city": None, "address": None}
    candidate = {"duration_hours": 1.5, "venue_name": "Marin FC Fields",
                 "city": None, "address": None}
    assert materially_conflicts(existing, candidate)


def test_materially_conflicts_clearly_different_duration_blocks_adoption():
    existing = {"duration_hours": 1.0, "venue_name": None, "city": None, "address": None}
    candidate = {"duration_hours": 2.0, "venue_name": None, "city": None, "address": None}
    assert materially_conflicts(existing, candidate)


def test_materially_conflicts_tolerates_small_duration_rounding():
    """A few minutes' difference from rounding/manual entry isn't a real
    conflict — only a clear disagreement is."""
    existing = {"duration_hours": 1.5, "venue_name": None, "city": None, "address": None}
    candidate = {"duration_hours": 1.6, "venue_name": None, "city": None, "address": None}
    assert not materially_conflicts(existing, candidate)
