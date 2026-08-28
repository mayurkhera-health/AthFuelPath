"""
Shared event-equivalence/reconciliation matcher.

The single place that answers "is this the same event I already have on
this athlete's schedule" — used by both the connected-calendar sync
(ics_sync.py's sync_platform, for every platform: byga, playmetrics, any
future provider) and the direct event-create endpoint
(routes/events.py's create_event, the standalone mobile ICS import's and
the manual add-event form's entry point). Both paths delegate to this
module instead of keeping their own slightly-different duplicate checks —
the backend is the final safety net regardless of which client behavior
caused a submission to arrive uid-less or with a rotated uid.

Conservative by design:
  * exact uid match is always tried first, upstream of this module (the
    partial unique index on (athlete_id, uid) IS that check — this module
    only runs when a row can't be found that way, i.e. no uid, or a uid
    that doesn't match any existing row);
  * every match still requires the SAME athlete, event_date, start_time,
    and event_type — this module only adds tolerance to the event_name
    comparison, never loosens the other fields;
  * name tolerance is PAIR-AWARE, not independent normalization of each
    side. Independently stripping a facility number or division code from
    BOTH names before comparing was this module's second draft and was
    rejected on review: "Complex #10" and "Complex #11" both strip down to
    "Complex" and would wrongly compare equal, even though the numbers
    conflict. The rule instead extracts the (base, number) for each side
    and only tolerates the difference when at most ONE side has a number
    in the recognized context:
      - both sides have a number and they DIFFER -> real difference,
        never tolerated (Field #1 / Field #2, G2008/09 / G2009/10);
      - one side has no number, the other does -> provider-noise
        tolerance applies (Complex / Complex #10);
      - neither side has a number -> unaffected, falls through to the
        next comparison layer.
  * the recognized "facility number" context is narrow and NOT "anywhere
    before a closing paren" (that was this module's third draft, rejected
    on review: "Tournament (Game #1)" / "Tournament (Game #2)" would
    falsely collapse — a parenthesized segment is not automatically a
    venue). The context is: the number immediately follows an explicit
    venue/facility keyword ("Complex #10", "Field #3", "(...Complex #10)"
    — parens or not, the keyword is what matters, not the parens).
  * fails closed: find_equivalent_event() distinguishes NO_MATCH from
    EXACTLY_ONE_MATCH from AMBIGUOUS_MATCH (a MatchResult, not a bare
    True/False/None) specifically so a caller can tell "safe to insert"
    apart from "duplicates already exist here — do not make it worse."
    Ambiguous is never resolved by guessing.
  * name/date/time/type/athlete matching alone is not sufficient grounds
    to silently treat two records as the same event for an ordinary manual
    create — materially_conflicts() adds a second, independent guard on
    duration/venue fields specifically for that decision. This is a
    SEPARATE check layered on top of names_equivalent(), not a change to
    it — see materially_conflicts()'s own docstring for why.
  * concurrent submissions of the same equivalent event must not race past
    each other into two rows — acquire_reconciliation_lock() takes a
    transaction-scoped Postgres advisory lock keyed to the (athlete, date,
    time, type) reconciliation scope a caller is about to check-then-write
    against, so a second concurrent caller for the SAME scope blocks until
    the first commits (and then sees its result), while a caller for a
    DIFFERENT scope (a genuinely different event) is never blocked.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# ── Facility/court-number tolerance — narrow context, pair-aware ────────────
# A bare "#<digits>" is NOT extracted everywhere — only where there is strong
# evidence it denotes a facility/venue/court, not a meaningful event/session
# number ("Tournament Game #1" vs "Tournament Game #2" must stay distinct).
# The context: the number immediately follows an explicit venue/facility
# keyword. This applies whether or not the whole thing sits inside parens —
# parens alone are never the signal (a parenthesized segment isn't
# automatically a venue: "Tournament (Game #1)" must NOT match "(Game #2)").
_VENUE_WORDS = (
    "complex", "field", "fields", "court", "courts", "park", "center",
    "centre", "facility", "stadium", "arena", "gym", "pool",
)
_FACILITY_NUMBER_RE = re.compile(
    r"\b(" + "|".join(_VENUE_WORDS) + r")\s*#\s*(\d+)\b"
)

# Division code tolerance — narrow context, pair-aware: a trailing token at
# the very end of the name, matching the actual observed provider behavior
# (an appended division/birth-year code, never a mid-name qualifier).
# Anchored to end-of-string so it can't coincidentally eat a division-shaped
# fragment that legitimately distinguishes two events elsewhere in the name.
_DIVISION_CODE_RE = re.compile(r"\s*\bg(\d{3,4}/\d{2})\b\s*$")

# Narrow, explicit allowlist of single trailing marker WORDS a provider is
# known to append after the real event name (a league/org affiliation tag —
# never part of what actually distinguishes one event from another).
# Deliberately NOT a general "any trailing word" rule: names_equivalent()
# only tolerates a name that differs from another by EXACTLY one extra
# trailing word, and only when that word is in this set. A session-type
# qualifier ("Advanced"), a makeup/reschedule marker ("Makeup"), a team
# letter ("JV", "Blue", "White"), or a game number ("1", "2") is never in
# this set, so those stay real differences.
_TRAILING_ORG_MARKERS = frozenset({"ecnl", "sc"})

# ECNL/RL competition-marker format tolerance — narrow, pair-aware, and
# distinct from _TRAILING_ORG_MARKERS above. Confirmed production gap
# (Nora / athlete 62): BYGA represents the SAME "ECNL-RL" competition marker
# in different textual forms across exports — "(ECNL-RL)" in one export,
# "ECNL RL" (plus the already-tolerated trailing division code) in another.
# This is a FORMAT variation of one marker, not a presence/absence drift, so
# unlike the facility-number/division-code extractions it never carries a
# conflicting value to compare — the three recognized forms all mean the
# same thing. To avoid ever confusing this with the single-word "ecnl"
# already in _TRAILING_ORG_MARKERS (which would wrongly let a bare "ECNL"
# name match an "ECNL-RL" name once the marker is stripped from only one
# side), this extraction requires the marker to be present on BOTH sides
# before stripping either — see the "both sides" branch in names_equivalent.
_ECNL_RL_MARKER_RE = re.compile(r"\s*(?:\(ecnl-rl\)|ecnl-rl|ecnl\s+rl)\s*$")


def _extract_ecnl_rl_marker(name: str) -> tuple[str, bool]:
    """If `name` ends with a recognized ECNL-RL marker form
    ("(ECNL-RL)", "ECNL-RL", or "ECNL RL"), return (name with that marker
    removed, True). Otherwise (name, False) unchanged. Call AFTER
    _extract_division_code, so "...ECNL RL G2013/14" has already had its
    division code stripped down to "...ECNL RL" before this runs."""
    m = _ECNL_RL_MARKER_RE.search(name)
    if not m:
        return name, False
    return name[: m.start()].rstrip(), True


def _basic_normalize(name: str | None) -> str:
    """Lowercase, trim, collapse internal whitespace. No token stripping —
    that's handled pair-aware by _extract_facility_number/_extract_division_code,
    which need to see both sides before deciding what's safe to remove."""
    return " ".join((name or "").strip().lower().split())


def _extract_facility_number(name: str) -> tuple[str, str | None]:
    """If `name` contains a facility number in the recognized venue-keyword
    context, return (name with "<keyword> #<n>" collapsed to "<keyword>",
    the extracted number as a string). Otherwise (name, None) unchanged.
    Only the FIRST match is extracted — realistic names have at most one."""
    m = _FACILITY_NUMBER_RE.search(name)
    if not m:
        return name, None
    base = name[: m.start()] + m.group(1) + name[m.end():]
    return " ".join(base.split()), m.group(2)


def _extract_division_code(name: str) -> tuple[str, str | None]:
    """If `name` ends with a division-code token, return (name with that
    trailing token removed, the extracted code). Otherwise (name, None)."""
    m = _DIVISION_CODE_RE.search(name)
    if not m:
        return name, None
    return name[: m.start()].rstrip(), m.group(1)


def normalize_event_name(name: str | None) -> str:
    """Best-effort single-string normalization, kept for callers that just
    want a display/logging-friendly canonical form (basic + both narrow
    extractions applied unconditionally). NOT used by names_equivalent() —
    that function needs both sides at once to stay pair-aware; applying
    this independently to each side is exactly the bug that made "Complex
    #10" and "Complex #11" compare equal in an earlier draft."""
    n = _basic_normalize(name)
    n, _ = _extract_facility_number(n)
    n, _ = _extract_division_code(n)
    return n


def names_equivalent(a: str | None, b: str | None) -> bool:
    """True if two event names are the same event.

    Pair-aware facility-number and division-code handling: for each of the
    two extractions, if BOTH sides carry a value and the values differ, the
    names are immediately treated as different (never tolerated) — this is
    the fix for "Complex #10" vs "Complex #11" and "G2008/09" vs
    "G2009/10". If at most one side carries a value, that value's token is
    stripped (provider-noise tolerance) and comparison continues on the
    stripped bases.

    After that: identical -> equivalent. Otherwise, one name may be exactly
    the other plus one trailing word from the explicit _TRAILING_ORG_MARKERS
    allowlist. Never a generic prefix/"starts with" check — any other
    difference, including a second extra word or an extra word not on the
    allowlist, is treated as a real difference.
    """
    na, nb = _basic_normalize(a), _basic_normalize(b)
    if not na or not nb:
        return False

    fac_base_a, fac_a = _extract_facility_number(na)
    fac_base_b, fac_b = _extract_facility_number(nb)
    if fac_a is not None and fac_b is not None and fac_a != fac_b:
        return False
    na, nb = fac_base_a, fac_base_b

    div_base_a, div_a = _extract_division_code(na)
    div_base_b, div_b = _extract_division_code(nb)
    if div_a is not None and div_b is not None and div_a != div_b:
        return False
    na, nb = div_base_a, div_base_b

    # ECNL-RL marker format tolerance — see _extract_ecnl_rl_marker's
    # docstring for why this requires the marker on BOTH sides, never just
    # one (that asymmetric case is exactly what would let a bare "ECNL" or
    # bare "RL" side wrongly collapse onto an "ECNL-RL" side).
    ecnl_rl_base_a, has_ecnl_rl_a = _extract_ecnl_rl_marker(na)
    ecnl_rl_base_b, has_ecnl_rl_b = _extract_ecnl_rl_marker(nb)
    if has_ecnl_rl_a and has_ecnl_rl_b:
        na, nb = ecnl_rl_base_a, ecnl_rl_base_b

    if na == nb:
        return True
    shorter_words, longer_words = (
        (na.split(), nb.split()) if len(na) <= len(nb) else (nb.split(), na.split())
    )
    if len(longer_words) != len(shorter_words) + 1:
        return False
    if longer_words[:-1] != shorter_words:
        return False
    return longer_words[-1] in _TRAILING_ORG_MARKERS


# ── Material-field conflict guard (Issue 4) ──────────────────────────────────
# A SEPARATE check from names_equivalent(). Name/date/time/type/athlete
# already matching is not, on its own, sufficient grounds to silently adopt
# an existing row instead of creating a new one — an athlete must still be
# able to deliberately create two genuinely different sessions that happen
# to share all of those fields. This function looks at fields
# names_equivalent() never sees (duration, venue/location) to decide whether
# the two records actually conflict. Conservative in the direction that
# matters here: missing data on either side is never treated as a conflict
# (an ICS import legitimately omits fields a manual entry might have, or
# vice versa) — only a clear disagreement between two NON-EMPTY values on
# both sides counts.
_DURATION_CONFLICT_TOLERANCE_HOURS = 0.26  # >15 min apart counts as a real difference


def materially_conflicts(existing: dict, candidate: dict) -> bool:
    """True if `existing` (a matched row) and `candidate` (the incoming
    submission's relevant fields — same keys: duration_hours, venue_name,
    city, address) disagree clearly enough that they should NOT be treated
    as the same event, even though names_equivalent() + the athlete/date/
    time/type filter already matched them. Missing data on either side is
    never a conflict — only two non-empty, clearly different values are."""
    e_dur = existing.get("duration_hours")
    c_dur = candidate.get("duration_hours")
    if e_dur is not None and c_dur is not None:
        if abs(float(e_dur) - float(c_dur)) > _DURATION_CONFLICT_TOLERANCE_HOURS:
            return True

    for field in ("venue_name", "city", "address"):
        e_val = (existing.get(field) or "").strip().lower()
        c_val = (candidate.get(field) or "").strip().lower()
        if e_val and c_val and e_val != c_val:
            return True

    return False


class MatchStatus(Enum):
    NO_MATCH = "no_match"
    EXACTLY_ONE_MATCH = "exactly_one_match"
    AMBIGUOUS_MATCH = "ambiguous_match"


@dataclass(frozen=True)
class MatchResult:
    """Outcome of find_equivalent_event(). `row` is set only when status is
    EXACTLY_ONE_MATCH. `candidate_count` is always the raw number of
    equivalent rows found (0, 1, or 2+) — callers that just want a count for
    logging/reporting don't need to re-derive it from status. `rows` holds
    ALL matched rows for AMBIGUOUS_MATCH (empty otherwise) — a caller that
    skips inserting/adopting on ambiguity still needs to know which existing
    rows it left alone, e.g. to exclude them from an unrelated cleanup sweep
    that would otherwise delete them for looking "gone from the feed"."""
    status: MatchStatus
    row: dict | None = None
    candidate_count: int = 0
    rows: tuple = ()


def find_equivalent_event(
    conn,
    athlete_id: int,
    event_date: str,
    start_time: str | None,
    event_type: str,
    event_name: str,
    source_sql: str,
    source_params: tuple = (),
) -> MatchResult:
    """Find existing row(s) that are the same event as the one described,
    restricted to rows matching `source_sql` (a SQL boolean fragment using
    %s placeholders, e.g. "source = %s" with (platform,), or the literal
    "source = 'manual'" with no params).

    Requires athlete_id + event_date + start_time + event_type to match
    exactly; event_name is compared via names_equivalent(). Returns a
    MatchResult so a caller can distinguish "no match — safe to insert" from
    "ambiguous — duplicates already exist, do not make it worse" from
    "exactly one match — safe to adopt" — collapsing the last two into a
    single falsy value was an earlier design's bug: a caller that just
    checked "is it None" could not tell those apart, so an ambiguous
    situation and a genuinely-new event were treated identically and both
    fell through to INSERT.

    Name equivalence only — this function does NOT apply
    materially_conflicts(); callers that need that guard (see
    routes/events.py's create_event) apply it themselves against the
    returned row, since only some callers have the extra candidate fields
    (duration/venue) to check against.

    NO_MATCH is also returned (with candidate_count=0, no log) if
    start_time is missing, since an all-day/untimed event has no reliable
    time key to match on and a NULL-time match would be far too loose.
    """
    if not start_time:
        return MatchResult(MatchStatus.NO_MATCH, candidate_count=0)

    rows = conn.execute(
        f"SELECT * FROM events WHERE athlete_id=%s AND event_date=%s AND start_time=%s "
        f"AND event_type=%s AND {source_sql}",
        (athlete_id, event_date, start_time, event_type, *source_params),
    ).fetchall()
    matches = [dict(r) for r in rows if names_equivalent(r["event_name"], event_name)]

    if len(matches) == 1:
        return MatchResult(MatchStatus.EXACTLY_ONE_MATCH, row=matches[0], candidate_count=1)
    if len(matches) > 1:
        logger.warning(
            "Event-equivalence match ambiguous (%s): %d candidates for athlete=%s "
            "event_name=%r date=%s time=%s type=%s — skipping, no auto-adopt.",
            source_sql, len(matches), athlete_id, event_name, event_date, start_time, event_type,
        )
        return MatchResult(MatchStatus.AMBIGUOUS_MATCH, candidate_count=len(matches), rows=tuple(matches))
    return MatchResult(MatchStatus.NO_MATCH, candidate_count=0)


# ── Concurrency guard (Issue 5) ──────────────────────────────────────────────
def acquire_reconciliation_lock(
    conn, athlete_id: int, event_date: str, start_time: str | None, event_type: str,
) -> None:
    """Take a transaction-scoped Postgres advisory lock keyed to this exact
    (athlete, date, time, type) reconciliation scope, BEFORE checking for an
    equivalent event and inserting if none is found. Without this, two
    concurrent submissions of the same equivalent event (e.g. two rotated-uid
    imports racing each other) can both observe NO_MATCH and both insert —
    the check-then-write sequence has no atomicity on its own.

    pg_advisory_xact_lock auto-releases at COMMIT or ROLLBACK — callers don't
    need to (and shouldn't) release it manually. A second concurrent caller
    for the SAME scope blocks here until the first transaction ends, then
    proceeds and sees the first caller's committed result. A caller for a
    DIFFERENT scope (athlete/date/time/type) is never blocked — this is not
    a global lock, and deliberately does not touch event_name, so it can't
    be used to block two genuinely-different same-time events from each
    other; it only serializes the reconcile-then-write race for what would
    otherwise be the same logical event.

    Deliberately NOT a DB uniqueness constraint (the codebase already
    rejected that approach — see this module's other docstrings — because
    it would block legitimate distinct same-time events). This is a lock
    around the RECONCILIATION DECISION, not a constraint on the data.

    No-op (returns immediately) if start_time is missing, matching
    find_equivalent_event's own "no reliable time key" stance — nothing
    downstream does a name-based match without a time key either.
    """
    if not start_time:
        return
    # advisory locks take two int32 keys; athlete_id is already an int, and
    # hashtext() folds the (date, time, type) scope into a stable int32.
    conn.execute(
        "SELECT pg_advisory_xact_lock(%s, hashtext(%s))",
        (athlete_id, f"{event_date}|{start_time}|{event_type}"),
    )
