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
  * name tolerance is NOT "one name starts with the other" and NOT "strip
    any #number anywhere" — both were this module's earlier drafts and
    were rejected on review for silently merging real distinct events
    ("Practice" / "Practice Advanced", "Tournament Game #1" / "Tournament
    Game #2"). Tolerance is instead narrowly-scoped rules, each tied to a
    SPECIFIC observed provider behavior:
      1. a facility/court number is stripped ONLY in a recognized
         location context — immediately before a closing paren (the
         observed BYGA form, "...Complex #10)") or immediately after a
         known venue/facility word ("Complex #10", "Field #3") — see
         _FACILITY_NUMBER_RE / normalize_event_name(). A bare "#1"/"#2"
         after a non-venue word ("Game #1", "Match #1", "Session #1") is
         left untouched — that's a real session identifier, not noise.
      2. a division code is stripped ONLY as a trailing token at the very
         end of the (already venue-number-stripped) name — see
         _DIVISION_CODE_RE.
      3. after that, AT MOST one extra trailing WORD is tolerated, and
         only if it's in the explicit _TRAILING_ORG_MARKERS allowlist
         (currently: "ecnl", "sc") — see names_equivalent(). Two extra
         words, or one extra word not on the allowlist, is a real
         difference, not noise.
  * fails closed: find_equivalent_event() distinguishes NO_MATCH from
    EXACTLY_ONE_MATCH from AMBIGUOUS_MATCH (a MatchResult, not a bare
    True/False/None) specifically so a caller can tell "safe to insert"
    apart from "duplicates already exist here — do not make it worse."
    Ambiguous is never resolved by guessing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# ── Facility/court-number tolerance — narrow contexts only ──────────────────
# A bare "#<digits>" is NOT stripped everywhere — only where there is strong
# evidence it denotes a facility/venue/court, not a meaningful event/session
# number ("Tournament Game #1" vs "Tournament Game #2" must stay distinct).
#
# Two recognized contexts, matching the actual observed provider behavior:
#   (a) immediately before a closing paren — the observed BYGA form, where
#       the whole parenthesized group IS the venue: "...(Twin Creeks Sports
#       Complex #10)". The parenthetical-venue convention itself is the
#       evidence here, independent of which word precedes the number.
#   (b) immediately after an explicit, narrow venue/facility keyword —
#       "Complex #10", "Field #3", "Court #2" — even with no parens.
_FACILITY_NUMBER_BEFORE_PAREN_RE = re.compile(r"\s*#\s*\d+(?=\))")
_VENUE_WORDS = (
    "complex", "field", "fields", "court", "courts", "park", "center",
    "centre", "facility", "stadium", "arena", "gym", "pool",
)
_FACILITY_NUMBER_AFTER_VENUE_WORD_RE = re.compile(
    r"\b(" + "|".join(_VENUE_WORDS) + r")\s*#\s*\d+\b"
)

# Division code tolerance — narrow context only: a trailing token at the
# very end of the name (after venue-number stripping), matching the actual
# observed provider behavior (an appended division/birth-year code, never a
# mid-name qualifier). Anchored to end-of-string rather than "anywhere" so
# it can't coincidentally eat a division-shaped fragment that legitimately
# distinguishes two events elsewhere in the name.
_DIVISION_CODE_RE = re.compile(r"\s*\bg\d{3,4}/\d{2}\b\s*$")

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


def normalize_event_name(name: str | None) -> str:
    """Lowercase, trim, collapse internal whitespace, and strip known
    provider-appended noise tokens ONLY in their recognized narrow contexts
    (a facility/court number immediately before a closing paren or right
    after a venue keyword; a division code as a trailing end-of-string
    token). Anything else — a genuinely different word, a bare session
    number after a non-venue word, a different opponent name — is left
    untouched; names_equivalent() layers one additional, narrowly
    allowlisted trailing-word tolerance on top of this."""
    n = " ".join((name or "").strip().lower().split())
    n = _FACILITY_NUMBER_BEFORE_PAREN_RE.sub("", n)
    n = _FACILITY_NUMBER_AFTER_VENUE_WORD_RE.sub(lambda m: m.group(1), n)
    n = _DIVISION_CODE_RE.sub("", n)
    n = n.replace("( )", "").replace("()", "")
    return " ".join(n.split())


def names_equivalent(a: str | None, b: str | None) -> bool:
    """True if two event names are the same event: identical after
    normalize_event_name() (whitespace/case/narrow-noise-token tolerant), OR
    one is EXACTLY the other plus one trailing word from the explicit
    _TRAILING_ORG_MARKERS allowlist. Never a generic prefix/"starts with"
    check — any other difference, including a second extra word or an
    extra word not on the allowlist, is treated as a real difference."""
    na, nb = normalize_event_name(a), normalize_event_name(b)
    if not na or not nb:
        return False
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
    single falsy value was the earlier design's bug: a caller that just
    checked "is it None" could not tell those apart, so an ambiguous
    situation and a genuinely-new event were treated identically and both
    fell through to INSERT.

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
