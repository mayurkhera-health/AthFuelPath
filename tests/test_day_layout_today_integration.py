import os
os.environ["DB_PATH"] = ":memory:"
from datetime import datetime
from api.services.day_layout import build_day_layout, day_layout_v2_enabled


def test_flag_helper_reads_env(monkeypatch):
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    assert day_layout_v2_enabled() is True
    monkeypatch.delenv("DAY_LAYOUT_V2", raising=False)
    assert day_layout_v2_enabled() is False


def test_to_template_windows_shape():
    from api.services.day_layout import cards_to_template_windows
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    tw = cards_to_template_windows(res["cards"])
    assert tw and all({"key", "label", "category", "sort_time"} <= set(w) for w in tw)
    # event marker maps to a nudge-only (non-tappable) window
    ev_win = next(w for w in tw if w["category"] == "event")
    assert ev_win["is_nudge_only"] is True


# ── Flag-ON integration test: exercises the real build_today_view seam ─────────

import pytest

TARGET_DATE = "2026-06-27"


@pytest.fixture
def db_conn():
    """In-memory DB fixture: init schema + run migrations, yield connection."""
    from db.setup import init_db
    from api.services.db_migrations import run_all
    from api.database import get_conn
    keepalive = get_conn()
    init_db()
    run_all()
    yield keepalive
    keepalive.close()


_seed_counter = {"n": 0}


def _seed_athlete_and_event(conn):
    """Insert a parent + athlete + single afternoon practice for TARGET_DATE."""
    _seed_counter["n"] += 1
    email = f"dl_integration_{_seed_counter['n']}@example.com"
    parent_id = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES (%s, %s, sqlite_now(), TRUE) RETURNING id",
        ("Test Parent", email),
    ).fetchone()["id"]

    athlete_id = conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (parent_id, "Tester", 14, "boy", 120, 5, 4),
    ).fetchone()["id"]

    conn.execute(
        "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (athlete_id, "Afternoon Practice", "practice", TARGET_DATE, "15:00", 1.0),
    )
    conn.commit()
    return athlete_id


def test_build_today_view_flag_on_macro_focus(monkeypatch, db_conn):
    """
    C1 regression: with DAY_LAYOUT_V2=true, at least one tappable window must
    have a macro_focus that isn't 'Fuel Window' (e.g. 'High Carbs' for fuel_before).
    """
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from api.services.today_service import build_today_view

    athlete_id = _seed_athlete_and_event(db_conn)
    result = build_today_view(athlete_id, db_conn, today=TARGET_DATE)

    windows = result["windows"]
    assert windows, "Expected at least one window"

    macro_focuses = [w.get("macro_focus") for w in windows]
    assert any(mf and mf != "Fuel Window" for mf in macro_focuses), (
        f"All macro_focus values are 'Fuel Window' — C1 fix did not take effect. "
        f"Got: {macro_focuses}"
    )


def test_build_today_view_flag_on_event_marker(monkeypatch, db_conn):
    """
    C2 regression: with DAY_LAYOUT_V2=true, the event marker card must appear
    in the merged windows list with window_type='event' and status='event'.
    """
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from api.services.today_service import build_today_view

    athlete_id = _seed_athlete_and_event(db_conn)
    result = build_today_view(athlete_id, db_conn, today=TARGET_DATE)

    windows = result["windows"]
    event_windows = [w for w in windows if w.get("window_type") == "event" or w.get("status") == "event"]
    assert event_windows, (
        f"No event-marker window found in windows list — C2 fix did not take effect. "
        f"window_types present: {[w.get('window_type') for w in windows]}"
    )


def test_build_today_view_uses_client_now_for_2h_resolver(monkeypatch):
    """Client-supplied now is threaded into build_day_layout (not server clock).

    We verify by monkeypatching build_day_layout to capture the `now` argument
    it receives. The test event has no activity_type (untagged), so the resolver's
    2-hour gate is exercised: before the gate (11:00 vs 15:00 start) and after
    (13:30 vs 15:00). What matters is that build_day_layout receives the CLIENT
    now — not a freshly-minted datetime.now() from the server.
    """
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    from db.setup import init_db
    from api.services.db_migrations import run_all
    import api.services.day_layout as _dl_mod

    captured_nows = []
    _real_build = _dl_mod.build_day_layout

    def _spy_build(events, athlete, now):
        captured_nows.append(now)
        return _real_build(events, athlete, now=now)

    monkeypatch.setattr(_dl_mod, "build_day_layout", _spy_build)

    conn = get_conn(); init_db(); run_all()
    conn.execute("INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES ('P','c1@x.com',sqlite_now(),TRUE)")
    pid = conn.execute("SELECT id FROM parents WHERE email='c1@x.com'").fetchone()["id"]
    conn.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
                 "VALUES (%s, 'A', 14, 'boy', 120, 5, 4)", (pid,))
    aid = conn.execute("SELECT id FROM athletes WHERE parent_id=%s", (pid,)).fetchone()["id"]
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
                 "VALUES (%s, 'Practice', 'practice', '2026-06-27', '15:00', 1.0)", (aid,))
    conn.commit()

    early_now = datetime(2026, 6, 27, 11, 0)
    late_now  = datetime(2026, 6, 27, 13, 30)

    early = build_today_view(aid, conn, today="2026-06-27", now=early_now)
    late  = build_today_view(aid, conn, today="2026-06-27", now=late_now)
    conn.close()

    assert early is not None and late is not None, "build_today_view returned None"
    assert len(captured_nows) == 2, f"Expected 2 spy calls, got {len(captured_nows)}"
    assert captured_nows[0] == early_now, (
        f"build_day_layout received wrong now on first call: {captured_nows[0]!r}"
    )
    assert captured_nows[1] == late_now, (
        f"build_day_layout received wrong now on second call: {captured_nows[1]!r}"
    )


def test_keep_going_renders_as_oz_packets_nudge():
    from api.services.day_layout import build_day_layout, cards_to_template_windows
    from datetime import datetime
    ev = {"id": 1, "event_type": "game", "activity_type": "game",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.5}  # 90 min → keep_going
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    kg = next(c for c in res["cards"] if c["card"] == "keep_going")
    assert kg.get("athlete_label") and "oz" in kg["athlete_label"].lower()

    tw = cards_to_template_windows(res["cards"])
    kg_win = next(w for w in tw if w["category"] == "keep_going")
    assert kg_win["is_nudge_only"] is True
    assert "oz" in kg_win["macro_focus"].lower()


def test_cards_to_template_windows_populates_open_close_from_date():
    from api.services.day_layout import build_day_layout, cards_to_template_windows
    from datetime import datetime
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    tw = cards_to_template_windows(res["cards"], "2026-06-27")
    fb = next(w for w in tw if w["key"] == "fuel_before")
    assert fb["open_dt"] is not None and fb["close_dt"] is not None
    assert fb["open_dt"].strftime("%H:%M") == fb["sort_time"]
    assert fb["close_dt"] > fb["open_dt"]


def test_cards_to_template_windows_open_close_none_without_date():
    from api.services.day_layout import build_day_layout, cards_to_template_windows
    from datetime import datetime
    ev = {"id": 1, "event_type": "practice", "activity_type": "practice",
          "event_date": "2026-06-27", "start_time": "15:00", "duration_hours": 1.0}
    res = build_day_layout([ev], {"id": 1, "weight_lbs": 120, "height_ft": 5,
                                  "height_in": 4, "gender": "boy", "age": 14},
                           now=datetime(2026, 6, 27, 6, 0))
    tw = cards_to_template_windows(res["cards"])   # no date_str → open/close stay None
    assert all(w["open_dt"] is None for w in tw)


def _seed_athlete_with_event(conn, email, event_type, activity_type, start="15:00"):
    from db.setup import init_db
    from api.services.db_migrations import run_all
    init_db(); run_all()
    conn.execute("INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) VALUES ('P',%s,sqlite_now(),TRUE)", (email,))
    pid = conn.execute("SELECT id FROM parents WHERE email=%s", (email,)).fetchone()["id"]
    conn.execute("INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
                 "VALUES (%s, 'A', 14, 'boy', 120, 5, 4)", (pid,))
    aid = conn.execute("SELECT id FROM athletes WHERE parent_id=%s", (pid,)).fetchone()["id"]
    conn.execute("INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours, activity_type) "
                 "VALUES (%s, 'E', %s, '2026-06-27', %s, 1.5, %s)", (aid, event_type, start, activity_type))
    conn.commit()
    return aid


def _spy_calc_daily_targets(monkeypatch):
    import api.services.today_service as ts
    captured = {}
    real = ts.calc_daily_targets
    def spy(athlete, event_type="rest", intensity=None, duration_min=0, **kw):
        captured["event_type"] = event_type
        captured["activity_type"] = kw.get("activity_type")
        return real(athlete, event_type, intensity, duration_min, **kw)
    monkeypatch.setattr(ts, "calc_daily_targets", spy)
    return captured


def test_flag_on_targets_use_real_event_type_and_resolved_tag(monkeypatch):
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    conn = get_conn()
    aid = _seed_athlete_with_event(conn, "d1@x.com", "game", "game")
    captured = _spy_calc_daily_targets(monkeypatch)
    build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 14, 0))
    conn.close()
    assert captured["event_type"] == "game"
    assert captured["activity_type"] == "game"


def test_flag_on_active_recovery_tag_threaded(monkeypatch):
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    conn = get_conn()
    aid = _seed_athlete_with_event(conn, "d2@x.com", "practice", "active_recovery", start="10:00")
    captured = _spy_calc_daily_targets(monkeypatch)
    build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 9, 0))
    conn.close()
    assert captured["event_type"] == "practice"
    assert captured["activity_type"] == "active_recovery"


def test_flag_off_legacy_targets_unchanged(monkeypatch):
    monkeypatch.delenv("DAY_LAYOUT_V2", raising=False)
    from datetime import datetime
    from api.services.today_service import build_today_view
    from api.database import get_conn
    conn = get_conn()
    aid = _seed_athlete_with_event(conn, "d3@x.com", "game", "game")
    captured = _spy_calc_daily_targets(monkeypatch)
    build_today_view(aid, conn, today="2026-06-27", now=datetime(2026, 6, 27, 14, 0))
    conn.close()
    assert captured["activity_type"] is None
    assert captured["event_type"] != "game"   # legacy passes the day_type label, not raw "game"


# ── PATCH /athletes/:id/dismiss-wind-down — regression for the missing route ──
# Mobile's "Skip forever" on the Evening Wind-Down card has always called this
# route; it never existed server-side, so the dismissal silently never stuck —
# the card just reappeared on the next refetch.

from fastapi.testclient import TestClient
from api.main import app
from tests.conftest import auth_headers


def test_dismiss_wind_down_persists_and_suppresses_the_card(monkeypatch, db_conn):
    monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    from api.services.today_service import build_today_view

    athlete_id = _seed_athlete_and_event(db_conn)

    with TestClient(app) as client:
        r = client.patch(
            f"/api/athletes/{athlete_id}/dismiss-wind-down",
            headers=auth_headers("athlete", athlete_id=athlete_id),
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"wind_down_dismissed": True}

    row = db_conn.execute(
        "SELECT wind_down_dismissed FROM athletes WHERE id = %s", (athlete_id,)
    ).fetchone()
    assert row["wind_down_dismissed"] == 1

    result = build_today_view(athlete_id, db_conn, today=TARGET_DATE)
    windows = result["windows"]
    assert not any(w.get("slot_name") == "wind_down" or w.get("window_type") == "wind_down"
                   for w in windows), "wind_down card still present after dismissal"


# ── category_key canonical-vocabulary contract (both engines) ─────────────────
# window_load.load_levels_for() and idea_catalog.IDEAS's fallback section both
# expect category_key to be one of carb|hydrate|balanced|recovery. Before the
# day_layout.py fix, cards_to_template_windows() set category_key = category
# (fuel_before/quick_snack/everyday/...) — an unknown value to both consumers,
# silently defaulting fat_level_for() to MODERATE regardless of the window's
# real fueling purpose. These tests prove BOTH engines (DAY_LAYOUT_V2 on and
# off) emit only the canonical vocabulary, across every day type.

from api.services.window_load import FAT_LEVEL_BY_CATEGORY_KEY

_CANONICAL_CATEGORY_KEYS = {"carb", "hydrate", "balanced", "recovery"}

_DAY_TYPE_SCENARIOS = {
    "evening_practice": [("Practice", "practice", "18:00", 1.5)],
    "morning_practice":  [("Practice", "practice", "08:00", 1.5)],
    "game":              [("Game", "game", "14:00", 1.5)],
    "double_session":    [("AM Practice", "practice", "07:00", 1.0),
                           ("PM Practice", "practice", "18:00", 1.0)],
    "tournament":        [("Game 1", "game", "09:00", 1.0),
                           ("Game 2", "game", "12:30", 1.0)],
    "rest_day":          [],
}


def _seed_athlete_and_events(conn, events):
    _seed_counter["n"] += 1
    email = f"dl_catkey_{_seed_counter['n']}@example.com"
    parent_id = conn.execute(
        "INSERT INTO parents (full_name, email, consent_timestamp, consent_confirmed) "
        "VALUES (%s, %s, sqlite_now(), TRUE) RETURNING id",
        ("Test Parent", email),
    ).fetchone()["id"]

    athlete_id = conn.execute(
        "INSERT INTO athletes (parent_id, first_name, age, gender, weight_lbs, height_ft, height_in) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (parent_id, "Tester", 14, "boy", 120, 5, 4),
    ).fetchone()["id"]

    for name, etype, start, dur in events:
        conn.execute(
            "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (athlete_id, name, etype, TARGET_DATE, start, dur),
        )
    conn.commit()
    return athlete_id


@pytest.mark.parametrize("day_layout_v2", [True, False])
@pytest.mark.parametrize("scenario", list(_DAY_TYPE_SCENARIOS))
def test_category_key_is_always_canonical_vocabulary(monkeypatch, db_conn, scenario, day_layout_v2):
    if day_layout_v2:
        monkeypatch.setenv("DAY_LAYOUT_V2", "true")
    else:
        monkeypatch.delenv("DAY_LAYOUT_V2", raising=False)
    from api.services.today_service import build_today_view

    athlete_id = _seed_athlete_and_events(db_conn, _DAY_TYPE_SCENARIOS[scenario])
    result = build_today_view(athlete_id, db_conn, today=TARGET_DATE)

    tappable = [w for w in result["windows"] if w.get("status") not in ("nudge", "event")]
    for w in tappable:
        ck = w.get("category_key")
        assert ck in _CANONICAL_CATEGORY_KEYS, (
            f"[{scenario}, DAY_LAYOUT_V2={day_layout_v2}] {w['slot_name']} has "
            f"non-canonical category_key {ck!r} — must be one of {_CANONICAL_CATEGORY_KEYS}"
        )
        # load_levels must be derived from the SAME category_key the window carries,
        # not silently fall back to MODERATE for an unrecognized key.
        levels = w.get("load_levels")
        if levels is not None:
            assert levels["fats"] == FAT_LEVEL_BY_CATEGORY_KEY[ck], (
                f"[{scenario}, DAY_LAYOUT_V2={day_layout_v2}] {w['slot_name']} fats "
                f"load_level {levels['fats']!r} doesn't match the fat level for its "
                f"own category_key {ck!r} — load_levels not derived from the intended key"
            )


def test_dismiss_wind_down_404s_for_a_nonexistent_athlete(monkeypatch, db_conn):
    r_athlete_id = 999999
    with TestClient(app) as client:
        r = client.patch(
            f"/api/athletes/{r_athlete_id}/dismiss-wind-down",
            headers=auth_headers("athlete", athlete_id=r_athlete_id),
        )
        assert r.status_code == 404
