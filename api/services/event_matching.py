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
  * name tolerance is NOT "one name starts with the other" — that was this
    module's first draft and was rejected on review: it silently merges
    real distinct events too, e.g. "Practice" / "Practice Advanced", "U15
    Game" / "U15 Game Makeup", "Team A" / "Team A JV" all satisfy a plain
    prefix check. Tolerance is instead two narrowly-scoped rules, each
    tied to a SPECIFIC observed provider behavior, nothing more general:
      1. noise TOKENS stripped wherever they appear in the string
         (facility/court number "#10", division code "G2008/09") — see
         normalize_event_name();
      2. after that, AT MOST one extra trailing WORD is tolerated, and
         only if it's in the explicit _TRAILING_ORG_MARKERS allowlist
         (currently: "ecnl", "sc") — see names_equivalent(). Two extra
         words, or one extra word not on the allowlist, is a real
         difference, not noise.
  * fails closed: more than one candidate row is treated as no match at
    all (logged, not guessed at) rather than adopting one arbitrarily.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Provider-appended noise TOKENS observed in production, stripped wherever
# they occur in the string — NOT only at the very end. A provider may embed
# one inside a parenthesized venue name ("...Sports Complex #10)") rather
# than strictly appending after the whole string, so a purely trailing-only
# strip would miss it (confirmed: this exact case is the real Kabir/athlete-71
# production bug this module fixes).
_FACILITY_NUMBER_RE = re.compile(r"\s*#\s*\d+")
_DIVISION_CODE_RE = re.compile(r"\s*\bg\d{3,4}/\d{2}\b")

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
    provider-appended noise tokens (facility/court numbers like '#10',
    division codes like 'G2008/09') wherever they appear in the string.
    Anything else — a genuinely different word, a different opponent name —
    is left untouched; names_equivalent() layers one additional, narrowly
    allowlisted trailing-word tolerance on top of this."""
    n = " ".join((name or "").strip().lower().split())
    n = _FACILITY_NUMBER_RE.sub("", n)
    n = _DIVISION_CODE_RE.sub("", n)
    n = n.replace("( )", "").replace("()", "")
    return " ".join(n.split())


def names_equivalent(a: str | None, b: str | None) -> bool:
    """True if two event names are the same event: identical after
    normalize_event_name() (whitespace/case/known-noise-token tolerant), OR
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


def find_equivalent_event(
    conn,
    athlete_id: int,
    event_date: str,
    start_time: str | None,
    event_type: str,
    event_name: str,
    source_sql: str,
    source_params: tuple = (),
) -> dict | None:
    """Find a single existing row that is the same event as the one
    described, restricted to rows matching `source_sql` (a SQL boolean
    fragment using %s placeholders, e.g. "source = %s" with (platform,), or
    the literal "source = 'manual'" with no params).

    Requires athlete_id + event_date + start_time + event_type to match
    exactly; event_name is compared via names_equivalent(). Returns None —
    and logs a warning — if more than one row matches, rather than adopting
    one arbitrarily. Returns None (no log) if start_time is missing, since
    an all-day/untimed event has no reliable time key to match on and a
    NULL-time match would be far too loose.
    """
    if not start_time:
        return None

    rows = conn.execute(
        f"SELECT * FROM events WHERE athlete_id=%s AND event_date=%s AND start_time=%s "
        f"AND event_type=%s AND {source_sql}",
        (athlete_id, event_date, start_time, event_type, *source_params),
    ).fetchall()
    matches = [dict(r) for r in rows if names_equivalent(r["event_name"], event_name)]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            "Event-equivalence match ambiguous (%s): %d candidates for athlete=%s "
            "event_name=%r date=%s time=%s type=%s — skipping, no auto-adopt.",
            source_sql, len(matches), athlete_id, event_name, event_date, start_time, event_type,
        )
    return None
