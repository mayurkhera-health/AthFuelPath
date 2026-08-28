"""Tests for the calendar-sync reconcile (api/services/ics_sync.py).

Focus on the two correctness guarantees that make full add/update/delete safe:
  * past synced events are NEVER deleted (history preserved),
  * a failed/empty feed never wipes anything,
and that every mutation triggers a fuel-window recompute.
"""

from datetime import datetime, timezone, timedelta

import pytest

from api.database import get_conn
from api.services import ics_sync


# ─── helpers ──────────────────────────────────────────────────────────────────
def _fresh_conn():
    """Real (shared) Postgres connection, reset to a clean slate for this test.

    athletes/events already exist via db/postgres/001_baseline.sql (applied
    once per test session; TRUNCATEd once per module by conftest's
    module-scoped _fresh_db fixture) with every column this file needs
    (byga_ics_url/playmetrics_ics_url/source/synced_at included) — so unlike
    the old private in-memory SQLite DB (built from a minimal ad hoc schema
    and patched via the retired, PRAGMA-based
    _add_source_to_events/_add_calendar_sync_to_athletes migration helpers,
    which are a syntax error against Postgres), isolation here just means
    clearing the athlete-1 rows this file touches on the real tables.
    sync_platform() operates on the conn we pass, so this stays fully
    isolated from other test modules.
    """
    conn = get_conn()
    conn.execute("DELETE FROM events WHERE athlete_id = 1")
    conn.execute("DELETE FROM athletes WHERE id = 1")
    conn.execute(
        "INSERT INTO athletes (id, first_name, age, gender, weight_lbs, height_ft, height_in, competition_level) "
        "VALUES (1, 'Tester', 14, 'boy', 120, 5, 4, 'competitive_club')"
    )
    conn.commit()
    return conn


def _vevent(uid, dt_utc, summary, hours=1.5, status="CONFIRMED"):
    start = dt_utc.strftime("%Y%m%dT%H%M%SZ")
    end = (dt_utc + timedelta(hours=hours)).strftime("%Y%m%dT%H%M%SZ")
    return (f"BEGIN:VEVENT\nUID:{uid}\nDTSTART:{start}\nDTEND:{end}\n"
            f"SUMMARY:{summary}\nSTATUS:{status}\nLOCATION:Field, San Jose\nEND:VEVENT\n")


def _cal(*vevents):
    return "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//test//EN\n" + "".join(vevents) + "END:VCALENDAR\n"


@pytest.fixture(autouse=True)
def _spy_windows(monkeypatch):
    """Isolate reconcile from the heavy window engine; record recompute calls."""
    calls = []
    monkeypatch.setattr(ics_sync, "on_event_added_or_changed",
                        lambda aid, d, conn: calls.append((aid, d)))
    return calls


def _feed(monkeypatch, ics_text):
    monkeypatch.setattr(ics_sync, "fetch_ics_text", lambda url: ics_text)


NOW = datetime.now(timezone.utc)
FUT1 = NOW + timedelta(days=7)
FUT2 = NOW + timedelta(days=8)
PAST = NOW - timedelta(days=30)


# ─── tests ────────────────────────────────────────────────────────────────────
def test_insert_new_events_and_recompute(monkeypatch, _spy_windows):
    conn = _fresh_conn()
    _feed(monkeypatch, _cal(
        _vevent("g1", FUT1, "U10 vs Rivals - Game"),
        _vevent("p1", FUT2, "Team Practice"),
        _vevent("old", PAST, "Past Game"),               # skipped: past
        _vevent("x", FUT1, "Game", status="CANCELLED"),  # skipped: cancelled
    ))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    assert counts["inserted"] == 2 and counts["updated"] == 0 and counts["deleted"] == 0
    rows = conn.execute("SELECT uid, event_type, source FROM events ORDER BY uid").fetchall()
    assert [(r["uid"], r["event_type"], r["source"]) for r in rows] == [
        ("g1", "game", "byga"), ("p1", "practice", "byga")]
    # one recompute per affected day
    assert set(_spy_windows) == {(1, FUT1.strftime("%Y-%m-%d")), (1, FUT2.strftime("%Y-%m-%d"))}


def test_update_changed_event_only(monkeypatch, _spy_windows):
    conn = _fresh_conn()
    _feed(monkeypatch, _cal(_vevent("g1", FUT1, "Game")))
    ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")
    _spy_windows.clear()

    # Same feed again → no-op (no needless update / recompute).
    ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")
    assert _spy_windows == []

    # Now the game moves 2h later → exactly one update + recompute.
    _feed(monkeypatch, _cal(_vevent("g1", FUT1 + timedelta(hours=2), "Game")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")
    assert counts["updated"] == 1 and counts["inserted"] == 0
    assert len(_spy_windows) == 1


def test_future_removal_deletes_but_past_preserved(monkeypatch, _spy_windows):
    conn = _fresh_conn()
    # Seed one future + one PAST synced event directly.
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, "
                 "start_time, duration_hours, uid, source) VALUES "
                 "(1,'Future','game',%s, '10:00',1.5,'fut','byga')", (FUT1.strftime("%Y-%m-%d"),))
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, "
                 "start_time, duration_hours, uid, source) VALUES "
                 "(1,'History','game',%s, '10:00',1.5,'hist','byga')", (PAST.strftime("%Y-%m-%d"),))
    # Also a manual event with the SAME future date — must never be touched.
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, "
                 "start_time, duration_hours, uid, source) VALUES "
                 "(1,'Manual','practice',%s, '08:00',1.0,NULL,'manual')", (FUT1.strftime("%Y-%m-%d"),))
    conn.commit()

    # Feed no longer contains 'fut' (game cancelled/removed) and never had 'hist'.
    _feed(monkeypatch, _cal(_vevent("g2", FUT2, "New Game")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    assert counts["inserted"] == 1 and counts["deleted"] == 1
    remaining = {r["uid"] or r["source"] for r in
                 conn.execute("SELECT uid, source FROM events").fetchall()}
    assert "fut" not in remaining          # future removal deleted
    assert "hist" in remaining             # PAST preserved (history)
    assert "manual" in remaining           # manual never touched
    assert "g2" in remaining               # new one inserted


def test_failed_feed_never_deletes(monkeypatch, _spy_windows):
    conn = _fresh_conn()
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, "
                 "start_time, duration_hours, uid, source) VALUES "
                 "(1,'Future','game',%s, '10:00',1.5,'fut','byga')", (FUT1.strftime("%Y-%m-%d"),))
    conn.commit()

    def _boom(url):
        raise ConnectionError("network down")
    monkeypatch.setattr(ics_sync, "fetch_ics_text", _boom)

    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")
    assert counts["error"] is not None
    assert counts["deleted"] == 0
    # The event survives a transient failure.
    assert conn.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"] == 1
    assert _spy_windows == []


def test_name_time_fallback_adopts_manual_duplicate(monkeypatch, _spy_windows):
    """BYGA rotates UUID4 UIDs on every export. The sync must recognize an already-
    imported event by (name, date, start_time) and update it in place rather than
    inserting a duplicate row."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    # Pre-existing manual copy (source='manual', different UID from what BYGA will send).
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Team Practice','practice',%s,%s  ,1.5,'old-uid-from-client-import','manual')",
        (event_date, start_time),
    )
    conn.commit()
    manual_id = conn.execute("SELECT id FROM events").fetchone()["id"]

    # BYGA feed contains the same event but with a freshly-rotated UID.
    _feed(monkeypatch, _cal(_vevent("byga-new-uid", FUT1, "Team Practice")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    # Exactly one row — no duplicate inserted.
    rows = conn.execute("SELECT * FROM events").fetchall()
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"

    row = dict(rows[0])
    assert row["id"] == manual_id, "Existing row must be updated in place (same id)"
    assert row["uid"] == "byga-new-uid", "UID must be updated to the feed's UID"
    assert row["source"] == "byga", "Source must be updated to the platform"
    assert row["synced_at"] is not None, "synced_at must be stamped"
    assert row["event_date"] == event_date, "event_date must be preserved"

    # Counts: one update, zero inserts.
    assert counts["updated"] == 1
    assert counts["inserted"] == 0

    # Window recompute fired for the event date.
    assert (1, event_date) in _spy_windows


def test_name_time_fallback_skips_ambiguous_duplicates(monkeypatch, _spy_windows):
    """When two manual rows share (name, date, start_time) the fallback skips
    rather than adopting one arbitrarily — neither row's uid or source changes."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    for suffix in ("1", "2"):
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
            "start_time, duration_hours, uid, source) VALUES "
            "(1,'Team Practice','practice',%s,%s,1.5,%s,%s)",
            (event_date, start_time, f"old-uid-{suffix}", "manual"),
        )
    conn.commit()

    _feed(monkeypatch, _cal(_vevent("byga-new-uid", FUT1, "Team Practice")))
    ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    manual_rows = conn.execute(
        "SELECT uid FROM events WHERE source='manual' ORDER BY id"
    ).fetchall()
    assert len(manual_rows) == 2, "Both manual rows must survive the sync"
    assert {r["uid"] for r in manual_rows} == {"old-uid-1", "old-uid-2"}, \
        "Manual row UIDs must not be overwritten by the fallback"


def test_name_time_fallback_adopts_prior_byga_duplicate_on_uid_rotation(monkeypatch, _spy_windows):
    """The actual production bug: a PRIOR byga-sourced row (from an earlier
    sync) must also be adoptable by the fallback, not just manual rows —
    otherwise every periodic resync of a UID-rotating feed re-inserts the
    same events as "new" and re-fires the new-events notification email."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    # Row from a PRIOR byga sync — source='byga', uid from that earlier export.
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Team Practice','practice',%s,%s,1.5,'byga-uid-from-last-sync','byga')",
        (event_date, start_time),
    )
    conn.commit()
    prior_id = conn.execute("SELECT id FROM events").fetchone()["id"]

    # BYGA rotated the UID again on this export — same event, new uid.
    _feed(monkeypatch, _cal(_vevent("byga-rotated-uid", FUT1, "Team Practice")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT * FROM events").fetchall()
    assert len(rows) == 1, f"Expected 1 row (updated in place), got {len(rows)} — duplicate inserted"
    row = dict(rows[0])
    assert row["id"] == prior_id
    assert row["uid"] == "byga-rotated-uid"
    assert counts["updated"] == 1
    assert counts["inserted"] == 0, "Must not re-report this event as new"


def test_name_time_fallback_adopts_byga_row_despite_ambiguous_manual_dupes(monkeypatch, _spy_windows):
    """Confirmed live production bug: an athlete with TWO stale duplicate
    manual-source rows (from an old double-import, unrelated to the live
    sync) alongside the real byga-sourced row from the prior cycle. The
    manual dupes alone are ambiguous (2 matches), but the byga row is a
    clean single match — the same-platform tier must adopt via that row
    and never let unrelated manual clutter block it, or every cycle
    re-reports the event as new indefinitely."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    for suffix in ("1", "2"):
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
            "start_time, duration_hours, uid, source) VALUES "
            "(1,'Team Practice','practice',%s,%s,1.5,%s,%s)",
            (event_date, start_time, f"stale-manual-{suffix}", "manual"),
        )
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Team Practice','practice',%s,%s,1.5,'byga-uid-from-last-sync','byga')",
        (event_date, start_time),
    )
    conn.commit()
    byga_id = conn.execute("SELECT id FROM events WHERE source='byga'").fetchone()["id"]

    _feed(monkeypatch, _cal(_vevent("byga-rotated-uid", FUT1, "Team Practice")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    byga_row = dict(conn.execute("SELECT * FROM events WHERE id=%s", (byga_id,)).fetchone())
    assert byga_row["uid"] == "byga-rotated-uid", "Byga row must be adopted despite manual dupes"
    assert counts["updated"] == 1
    assert counts["inserted"] == 0, "Must not re-report as new because of unrelated manual clutter"

    manual_rows = conn.execute(
        "SELECT uid FROM events WHERE source='manual' ORDER BY id"
    ).fetchall()
    assert {r["uid"] for r in manual_rows} == {"stale-manual-1", "stale-manual-2"}, \
        "Stale manual rows must be left untouched"


def test_name_time_fallback_does_not_merge_across_platforms(monkeypatch, _spy_windows):
    """A row synced from a DIFFERENT platform (e.g. playmetrics) must never be
    adopted by a byga sync, even with matching name/date/time — that would
    silently reassign an event between the athlete's two connected feeds."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Team Practice','practice',%s,%s,1.5,'playmetrics-uid','playmetrics')",
        (event_date, start_time),
    )
    conn.commit()

    _feed(monkeypatch, _cal(_vevent("byga-uid", FUT1, "Team Practice")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT uid, source FROM events ORDER BY source").fetchall()
    assert len(rows) == 2, "Both the playmetrics row and the new byga row must exist separately"
    assert {r["source"] for r in rows} == {"playmetrics", "byga"}
    assert counts["inserted"] == 1
    assert counts["updated"] == 0


def test_name_time_fallback_tolerates_facility_suffix_drift(monkeypatch, _spy_windows):
    """Confirmed production bug (Kabir, athlete 71): a pre-existing manual row
    named '...Twin Creeks Sports Complex' and a BYGA export of the SAME
    practice named '...Twin Creeks Sports Complex #10' (BYGA appends a
    facility/court number the manual import never had) must be recognized as
    the same event via the shared event_matching tolerance, not inserted as
    a 3rd row."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Practice: Twin Creeks Sports Complex','practice',%s,%s,1.5,'old-manual-uid','manual')",
        (event_date, start_time),
    )
    conn.commit()
    manual_id = conn.execute("SELECT id FROM events").fetchone()["id"]

    _feed(monkeypatch, _cal(_vevent("byga-uid", FUT1, "Practice: Twin Creeks Sports Complex #10")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT * FROM events").fetchall()
    assert len(rows) == 1, f"Expected 1 row (adopted), got {len(rows)}"
    row = dict(rows[0])
    assert row["id"] == manual_id
    assert row["uid"] == "byga-uid"
    assert row["source"] == "byga"
    assert counts["updated"] == 1
    assert counts["inserted"] == 0


def test_name_time_fallback_tolerates_same_platform_rename(monkeypatch, _spy_windows):
    """Confirmed production bug: BYGA itself renamed events mid-season between
    two sync runs (e.g. 'U19/18 ECNL at Marin FC' -> 'U19/18 ECNL at Marin FC
    ECNL G2008/09', a division code appended). The same-platform fallback tier
    must adopt across that rename, not treat the renamed export as a new
    event and leave the old row orphaned."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    # guess_event_type("...Marin FC ECNL G2008/09") has no "game"/"match"
    # keyword, so it defaults to "practice" — matching the actual production
    # row's inferred type at insert time.
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'U19/18 ECNL at Marin FC','practice',%s,%s,1.5,'byga-uid-old-export','byga')",
        (event_date, start_time),
    )
    conn.commit()
    prior_id = conn.execute("SELECT id FROM events").fetchone()["id"]

    _feed(monkeypatch, _cal(_vevent(
        "byga-uid-new-export", FUT1, "U19/18 ECNL at Marin FC ECNL G2008/09",
    )))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT * FROM events").fetchall()
    assert len(rows) == 1, f"Expected 1 row (adopted despite rename), got {len(rows)}"
    row = dict(rows[0])
    assert row["id"] == prior_id
    assert row["uid"] == "byga-uid-new-export"
    assert row["event_name"] == "U19/18 ECNL at Marin FC ECNL G2008/09"
    assert counts["updated"] == 1
    assert counts["inserted"] == 0


def test_repeated_sync_cycles_keep_count_stable(monkeypatch, _spy_windows):
    """Re-running sync_platform 5 times in a row (uid rotates + name drifts a
    little more each cycle, worst-case realistic behavior) must never grow
    the row count past 1."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    names = [
        "Practice: Field House",
        "Practice: Field House #3",
        "Practice: Field House #3",
        "Practice: Field House #3 ECNL",
        "Practice: Field House #3 ECNL G2008/09",
    ]
    for i, name in enumerate(names):
        _feed(monkeypatch, _cal(_vevent(f"cycle-uid-{i}", FUT1, name)))
        ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT * FROM events WHERE athlete_id=1").fetchall()
    assert len(rows) == 1, f"Expected 1 row after 5 sync cycles, got {len(rows)}: {[dict(r) for r in rows]}"
    assert dict(rows[0])["uid"] == "cycle-uid-4", "Must be adopted under the LATEST cycle's uid"


def test_two_different_events_same_time_both_preserved_across_sync(monkeypatch, _spy_windows):
    """Two genuinely different pre-existing events (different opponents/names)
    at the same athlete/date/time/type must never be collapsed by a sync that
    only matches one of them."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    # guess_event_type("Soccer vs ...") has no "game"/"match" keyword, so it
    # defaults to "practice" — matching that here keeps event_type consistent
    # with what the feed side will parse, which is what the matcher requires.
    for name, uid in (("Soccer vs River City", "manual-uid-a"), ("Soccer vs Lakeside", "manual-uid-b")):
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
            "start_time, duration_hours, uid, source) VALUES "
            "(1,%s,'practice',%s,%s,1.5,%s,'manual')",
            (name, event_date, start_time, uid),
        )
    conn.commit()

    # BYGA export matches ONLY "Soccer vs River City" (with a trailing
    # allowlisted org-marker word — see _TRAILING_ORG_MARKERS in
    # event_matching.py; a made-up venue tag like "Field 2" is deliberately
    # NOT tolerated, so this test uses a real allowlisted word).
    _feed(monkeypatch, _cal(_vevent("byga-uid", FUT1, "Soccer vs River City SC")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT event_name, uid, source FROM events ORDER BY event_name").fetchall()
    assert len(rows) == 2, "Both distinct events must survive"
    by_name = {r["event_name"]: dict(r) for r in rows}
    assert "Soccer vs Lakeside" in by_name
    assert by_name["Soccer vs Lakeside"]["source"] == "manual", "Untouched event must stay manual"
    assert by_name["Soccer vs River City SC"]["source"] == "byga", "Matched event must be adopted"
    assert counts["updated"] == 1
    assert counts["inserted"] == 0


# ─── Issue 2: ambiguous matches must not multiply duplicates ───────────────

def test_ambiguous_manual_duplicates_do_not_multiply_on_sync(monkeypatch, _spy_windows):
    """Two pre-existing equivalent manual rows (already ambiguous — a stale
    double-import, unrelated to this sync) + a BYGA export of the same event
    with a rotated uid: the sync must NOT insert a 3rd row, and must NOT
    arbitrarily adopt one of the two manual rows either. 2 stays 2."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    for suffix in ("1", "2"):
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
            "start_time, duration_hours, uid, source) VALUES "
            "(1,'Team Practice','practice',%s,%s,1.5,%s,'manual')",
            (event_date, start_time, f"stale-manual-{suffix}"),
        )
    conn.commit()

    _feed(monkeypatch, _cal(_vevent("byga-new-uid", FUT1, "Team Practice")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT id, uid, source FROM events WHERE athlete_id=1").fetchall()
    assert len(rows) == 2, f"Expected 2 rows (unchanged), got {len(rows)}"
    assert {r["uid"] for r in rows} == {"stale-manual-1", "stale-manual-2"}, \
        "Neither existing row may be silently adopted/renamed"
    assert counts["inserted"] == 0, "Must not insert a 3rd duplicate"
    assert counts["updated"] == 0, "Must not arbitrarily adopt either existing row"
    assert counts["ambiguous_skipped"] == 1
    conn.close()


def test_ambiguous_same_platform_duplicates_do_not_multiply_on_resync(monkeypatch, _spy_windows):
    """Two pre-existing equivalent BYGA rows (a stale same-platform
    double-sync from before this fix existed) + a fresh resync with yet
    another rotated uid: must not insert a 3rd row."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    for suffix in ("1", "2"):
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
            "start_time, duration_hours, uid, source) VALUES "
            "(1,'Team Practice','practice',%s,%s,1.5,%s,'byga')",
            (event_date, start_time, f"stale-byga-{suffix}"),
        )
    conn.commit()

    _feed(monkeypatch, _cal(_vevent("byga-newest-uid", FUT1, "Team Practice")))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")

    rows = conn.execute("SELECT id, uid FROM events WHERE athlete_id=1").fetchall()
    assert len(rows) == 2, f"Expected 2 rows (unchanged), got {len(rows)}"
    assert {r["uid"] for r in rows} == {"stale-byga-1", "stale-byga-2"}
    assert counts["inserted"] == 0
    assert counts["updated"] == 0
    assert counts["ambiguous_skipped"] == 1
    conn.close()


def test_ambiguous_duplicates_stay_stable_across_5_resync_cycles(monkeypatch, _spy_windows):
    """A pre-existing ambiguous pair must not grow (2 -> 3 -> 4 -> ...) no
    matter how many times the provider resyncs with a new uid each time —
    the whole point of failing closed is that repeated syncs don't make an
    already-bad situation worse."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    for suffix in ("1", "2"):
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
            "start_time, duration_hours, uid, source) VALUES "
            "(1,'Team Practice','practice',%s,%s,1.5,%s,'manual')",
            (event_date, start_time, f"stale-manual-{suffix}"),
        )
    conn.commit()

    for i in range(5):
        _feed(monkeypatch, _cal(_vevent(f"cycle-uid-{i}", FUT1, "Team Practice")))
        counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive")
        assert counts["inserted"] == 0, f"cycle {i}: must not insert"
        assert counts["ambiguous_skipped"] == 1, f"cycle {i}: must report the ambiguity every cycle"
        rows = conn.execute("SELECT COUNT(*) AS n FROM events WHERE athlete_id=1").fetchone()
        assert rows["n"] == 2, f"cycle {i}: row count must stay at 2, got {rows['n']}"
    conn.close()


def test_migrations_idempotent():
    # The columns this used to add at runtime (twice, to prove idempotency)
    # via the retired SQLite-only helpers _add_calendar_sync_to_athletes /
    # _add_source_to_events (PRAGMA table_info + ALTER TABLE — a syntax
    # error against Postgres) are now just part of the baseline schema
    # (db/postgres/001_baseline.sql), applied once per test session. Assert
    # the real table already has that shape and that `source` still
    # defaults to 'manual' for a bare insert.
    conn = get_conn()
    acols = {
        r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'athletes'"
        ).fetchall()
    }
    ecols = {
        r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'events'"
        ).fetchall()
    }
    assert "byga_ics_url" in acols and "playmetrics_ics_url" in acols
    assert "source" in ecols and "synced_at" in ecols

    conn.execute("DELETE FROM events WHERE athlete_id = 1")
    conn.execute("DELETE FROM athletes WHERE id = 1")
    conn.execute(
        "INSERT INTO athletes (id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (1, 'Tester', 14, 'boy', 120, 5, 4)"
    )
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date) "
                 "VALUES (1, 'E', 'practice', '2026-06-27')")
    conn.commit()
    assert conn.execute("SELECT source FROM events WHERE athlete_id = 1").fetchone()["source"] == "manual"  # default
    conn.close()


# ─── Transaction isolation: a UniqueViolation must not roll back earlier
#     successful work from the SAME sync_platform() call ────────────────────
#
# sync_platform() reconciles a whole feed inside one open transaction —
# conn.commit() only happens once, after the full INSERT/UPDATE/DELETE loop.
# The INSERT path's UniqueViolation handler used to call conn.rollback() on
# that SAME outer transaction, which discards every uncommitted mutation
# from events processed earlier in the same call — while the Python
# `existing`/`counts` state is plain in-memory state, untouched by the DB
# rollback. That divergence is real and reproduced below.

def test_uid_collision_rollback_does_not_discard_earlier_rename(monkeypatch, _spy_windows):
    """The exact production failure class: one logical game, an exact-UID
    rename that succeeds first, an unrelated UID collision later in the SAME
    feed pull, then a rotated-UID re-export of the SAME game. Before the fix,
    the collision's rollback silently discards the earlier rename, so the
    rotated-UID event no longer finds an equivalent row and gets inserted as
    a second, duplicate logical row for the same game."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    # Existing row, deliberately NOT names_equivalent to the Marin FC name —
    # only the exact-UID update path (not the matcher) should touch it first.
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Legacy Marin Fixture','practice',%s,%s,1.5,'stable-existing-uid','byga')",
        (event_date, start_time),
    )
    # Unrelated manual row whose uid the second feed VEVENT will collide with.
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Totally Unrelated Manual Event','game','2099-01-01','09:00',"
        "1.5,'colliding-uid','manual')",
    )
    conn.commit()
    original_id = conn.execute(
        "SELECT id FROM events WHERE uid = 'stable-existing-uid'"
    ).fetchone()["id"]

    _feed(monkeypatch, _cal(
        # 1. Exact-UID rename — normal UPDATE path, not the matcher.
        _vevent("stable-existing-uid", FUT1, "U19/18 ECNL at Marin FC ECNL G2008/09"),
        # 2. Forces a UniqueViolation on INSERT (colliding uid, non-matching
        #    name/date/time so neither matcher tier adopts it first).
        _vevent("colliding-uid", NOW + timedelta(days=30), "Some Other Practice Entirely"),
        # 3. Rotated UID re-export of the SAME logical Marin FC game.
        _vevent("rotated-marin-uid", FUT1, "U19/18 ECNL at Marin FC"),
    ))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive_club")

    marin_rows = conn.execute(
        "SELECT id, event_name, uid FROM events WHERE id = %s "
        "OR (event_date = %s AND start_time = %s AND event_type = 'practice' AND source = 'byga')",
        (original_id, event_date, start_time),
    ).fetchall()
    assert len(marin_rows) == 1, (
        f"Expected exactly 1 logical Marin FC row after the rename+collision+rotation "
        f"sequence, got {len(marin_rows)}: {[dict(r) for r in marin_rows]}"
    )
    row = dict(marin_rows[0])
    assert row["id"] == original_id, (
        "The original row must be the one still standing (no duplicate row for "
        "the same logical game) — id must survive the whole rename+collision+"
        "rotation sequence unchanged"
    )
    # VEVENT 3 (rotated uid, short name) is the LAST event reconciled for this
    # slot — since the fix makes VEVENT 1's rename actually persist, VEVENT 3's
    # matcher lookup correctly finds `original_id` as EXACTLY_ONE_MATCH (long
    # vs short name, already proven names_equivalent()==True) and adopts it,
    # updating uid + name to VEVENT 3's version. That's the correct, intended
    # end state — one row, tracking the latest export.
    assert row["uid"] == "rotated-marin-uid"
    assert row["event_name"] == "U19/18 ECNL at Marin FC"
    assert counts["inserted"] == 0, (
        "The rotated-UID re-export of the SAME game must never be reported as a new event"
    )


def test_uid_collision_does_not_revert_earlier_successful_update(monkeypatch, _spy_windows):
    """Simpler form of the same defect (the A2 lost-update repro): a
    successful match+update, followed by an unrelated UID collision later in
    the same feed. The earlier update must remain persisted, and counts must
    never claim a persisted update that was actually rolled back."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'U19/18 ECNL at Marin FC ECNL G2008/09','practice',%s,%s,1.5,'old-uid-14991','byga')",
        (event_date, start_time),
    )
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Totally Unrelated Manual Event','game','2099-01-01','09:00',"
        "1.5,'colliding-uid','manual')",
    )
    conn.commit()
    marin_id = conn.execute(
        "SELECT id FROM events WHERE uid = 'old-uid-14991'"
    ).fetchone()["id"]

    _feed(monkeypatch, _cal(
        # Rotated-UID re-export, adopted via the matcher (name+date+time+type).
        _vevent("new-rotated-uid", FUT1, "U19/18 ECNL at Marin FC"),
        # Later, unrelated collision forces a UniqueViolation.
        _vevent("colliding-uid", NOW + timedelta(days=30), "Some Other Practice Entirely"),
    ))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive_club")

    row = dict(conn.execute("SELECT * FROM events WHERE id = %s", (marin_id,)).fetchone())
    assert row["uid"] == "new-rotated-uid", (
        "The earlier successful adoption/update must survive the later UniqueViolation"
    )
    assert row["event_name"] == "U19/18 ECNL at Marin FC"
    if counts["updated"] >= 1:
        # If counts claim an update happened, it must actually be persisted —
        # never a case of "counts say updated=1 but Postgres reverted it."
        assert row["uid"] == "new-rotated-uid"


def test_uid_collision_upgrade_and_neighbors_all_persist(monkeypatch, _spy_windows):
    """The core transaction-safety contract: event A updates successfully,
    event B triggers a UID collision (handled via the existing
    source-upgrade fallback), event C reconciles afterward. After the sync
    finishes, all three outcomes must be persisted and the connection must
    remain usable."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    # A: existing byga row that will be renamed via exact-UID update.
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Practice A (old name)','practice',%s,%s,1.5,'uid-a','byga')",
        (event_date, start_time),
    )
    # B: manual row whose uid the feed will collide with.
    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
        "start_time, duration_hours, uid, source) VALUES "
        "(1,'Practice B (manual entry)','practice','2099-02-02','11:00',"
        "1.5,'uid-b','manual')",
    )
    conn.commit()
    a_id = conn.execute("SELECT id FROM events WHERE uid = 'uid-a'").fetchone()["id"]
    b_id = conn.execute("SELECT id FROM events WHERE uid = 'uid-b'").fetchone()["id"]

    _feed(monkeypatch, _cal(
        _vevent("uid-a", FUT1, "Practice A (renamed)"),                     # A: exact-uid update
        _vevent("uid-b", NOW + timedelta(days=40), "Practice B (renamed)"), # B: forces UniqueViolation
        _vevent("uid-c", FUT2, "Practice C (brand new)"),                   # C: plain new insert
    ))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive_club")

    a = dict(conn.execute("SELECT * FROM events WHERE id = %s", (a_id,)).fetchone())
    assert a["event_name"] == "Practice A (renamed)", "A's update must persist"

    b = dict(conn.execute("SELECT * FROM events WHERE id = %s", (b_id,)).fetchone())
    assert b["source"] == "byga", "B must be upgraded to the platform source"
    assert counts["source_upgraded"] == 1

    c_rows = conn.execute(
        "SELECT * FROM events WHERE uid = 'uid-c' AND event_name = 'Practice C (brand new)'"
    ).fetchall()
    assert len(c_rows) == 1, "C must be inserted exactly once"
    assert counts["inserted"] == 1
    assert counts["inserted_events"] == [
        {"event_name": "Practice C (brand new)", "event_date": FUT2.strftime("%Y-%m-%d"),
         "event_type": "practice"},
    ], "inserted_events must list only the genuinely-inserted event, never the collided one"

    # Connection must remain usable after the caught UniqueViolation.
    assert conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1


# ─── Same-feed multiplicity: two UIDs for the same logical game in ONE pull ──

def test_same_feed_two_uids_for_one_logical_game_dedupes_to_one_row(monkeypatch, _spy_windows):
    """A single feed pull that (as BYGA has been observed to do) carries TWO
    separate VEVENTs — different UIDs, equivalent names — for the same
    logical game. Starting from an empty DB, this must converge to exactly
    one row: the first VEVENT inserts, the second is adopted by the matcher
    (which queries the live DB, not the start-of-call `existing` snapshot),
    not inserted as a second row."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    _feed(monkeypatch, _cal(
        _vevent("uid-long-form", FUT1, "U19/18 ECNL at Marin FC ECNL G2008/09"),
        _vevent("uid-short-form", FUT1, "U19/18 ECNL at Marin FC"),
    ))
    counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive_club")

    rows = conn.execute(
        "SELECT id, event_name, uid FROM events WHERE athlete_id = 1 "
        "AND event_date = %s AND start_time = %s", (event_date, start_time),
    ).fetchall()
    assert len(rows) == 1, f"Expected 1 logical row, got {len(rows)}: {[dict(r) for r in rows]}"
    assert counts["inserted"] == 1
    assert counts["updated"] == 1


def test_same_feed_two_uids_stable_across_5_resync_cycles(monkeypatch, _spy_windows):
    """The same two-VEVENT-per-game feed, resynced 5 times with rotating
    order/uids. After the first genuine insertion, later cycles must never
    grow the row count or re-report the game as newly inserted."""
    conn = _fresh_conn()
    event_date = FUT1.strftime("%Y-%m-%d")
    start_time = FUT1.strftime("%H:%M")

    cycles = [
        (("uid-long-1", "U19/18 ECNL at Marin FC ECNL G2008/09"),
         ("uid-short-1", "U19/18 ECNL at Marin FC")),
        (("uid-short-2", "U19/18 ECNL at Marin FC"),
         ("uid-long-2", "U19/18 ECNL at Marin FC ECNL G2008/09")),
        (("uid-long-3", "U19/18 ECNL at Marin FC ECNL G2008/09"),
         ("uid-short-3", "U19/18 ECNL at Marin FC")),
        (("uid-short-4", "U19/18 ECNL at Marin FC"),
         ("uid-long-4", "U19/18 ECNL at Marin FC ECNL G2008/09")),
        (("uid-long-5", "U19/18 ECNL at Marin FC ECNL G2008/09"),
         ("uid-short-5", "U19/18 ECNL at Marin FC")),
    ]
    for i, (first, second) in enumerate(cycles):
        _feed(monkeypatch, _cal(_vevent(first[0], FUT1, first[1]), _vevent(second[0], FUT1, second[1])))
        counts = ics_sync.sync_platform(conn, 1, "byga", "http://x", "competitive_club")
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE athlete_id = 1 "
            "AND event_date = %s AND start_time = %s", (event_date, start_time),
        ).fetchone()
        assert rows["n"] == 1, f"cycle {i}: row count must stay at 1, got {rows['n']}"
        if i > 0:
            assert counts["inserted"] == 0, f"cycle {i}: must not re-report the logical game as new"
    conn.close()
