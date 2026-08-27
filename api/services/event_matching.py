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
  * name tolerance is limited to whitespace/case and a TRAILING suffix a
    provider appended (facility/court number, division code, org
    abbreviation — "...Complex" -> "...Complex #10", "San Juan" ->
    "San Juan SC", "...Marin FC" -> "...Marin FC ECNL G2008/09"). A name
    is never truncated or rewritten from the middle, so two genuinely
    different events ("vs Team A" / "vs Team B") never collide;
  * fails closed: more than one candidate row is treated as no match at
    all (logged, not guessed at) rather than adopting one arbitrarily.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Provider-appended noise tokens observed in production, stripped wherever
# they occur in the string — NOT only at the very end. A provider may embed
# one inside a parenthesized venue name ("...Sports Complex #10)") rather
# than strictly appending after the whole string, so a purely trailing-only
# strip would miss it (confirmed: this exact case is the real Kabir/athlete-71
# production bug this module fixes).
_FACILITY_NUMBER_RE = re.compile(r"\s*#\s*\d+")
_DIVISION_CODE_RE = re.compile(r"\s*\bg\d{3,4}/\d{2}\b")


def normalize_event_name(name: str | None) -> str:
    """Lowercase, trim, collapse internal whitespace, and strip known
    provider-appended noise tokens (facility/court numbers like '#10',
    division codes like 'G2008/09') wherever they appear in the string.
    Anything else — a genuinely different word, a different opponent name —
    is left untouched; names_equivalent() layers additional trailing-text
    tolerance on top of this for provider renames this regex doesn't cover
    (e.g. an appended org abbreviation)."""
    n = " ".join((name or "").strip().lower().split())
    n = _FACILITY_NUMBER_RE.sub("", n)
    n = _DIVISION_CODE_RE.sub("", n)
    n = n.replace("( )", "").replace("()", "")
    return " ".join(n.split())


def names_equivalent(a: str | None, b: str | None) -> bool:
    """True if two event names are the same event, allowing for a provider
    having appended a trailing facility/division/org marker to one of them
    since the other was captured. Every word the shorter name has must
    match the longer name's leading words exactly — only whole trailing
    words may be added, never removed or altered mid-string."""
    na, nb = normalize_event_name(a), normalize_event_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return longer.startswith(shorter + " ")


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
