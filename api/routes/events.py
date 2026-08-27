import psycopg
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from api.models import EventCreate, EventUpdate, EventResponse, ActivityTypePatch
from api.database import get_conn
from api.services import ics_sync
from api.services.window_templates import on_event_added_or_changed
from api.services.nutrition_calc import derive_intensity
from api.services.session_auth import require_session, assert_owns_athlete
from api.services.event_matching import find_equivalent_event

router = APIRouter()


@router.get("/fetch-ics")
def fetch_ics(url: str, identity=Depends(require_session)):
    # Reuses ics_sync.fetch_ics_text — same webcal:// normalization + SSRF guard
    # (host re-validated on every redirect hop, rejects loopback/private/
    # link-local/reserved/multicast/unspecified addresses, incl. the cloud
    # metadata IP) already relied on by the authenticated calendar-sync route.
    # No athlete_id is involved here (this is a standalone URL preview/validate
    # fetch), so require_session alone — not assert_owns_athlete — is the
    # correct gate: it just needs a real caller, not a specific ownership check.
    try:
        content = ics_sync.fetch_ics_text(url)
        return {"content": content}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Could not fetch calendar: {str(e)}")


@router.post("/", response_model=EventResponse, status_code=201)
def create_event(data: EventCreate, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        athlete = conn.execute(
            "SELECT id, competition_level FROM athletes WHERE id = %s", (data.athlete_id,)
        ).fetchone()
        if not athlete:
            raise HTTPException(404, "Athlete not found.")

        intensity = data.intensity or derive_intensity(data.event_type, athlete["competition_level"])

        # Backend safety net: recognize an already-on-schedule event even when
        # the caller sent no uid, or a uid the source calendar has since
        # rotated. The standalone mobile ICS import (utils/icsImport.ts) sends
        # no uid at all when a VEVENT lacks one, and re-importing a
        # UID-rotating feed sends a brand-new uid every time either way —
        # client-side pre-checks can't catch what the client itself can't
        # tell is a repeat. Uses the same conservative event-equivalence rule
        # the connected-calendar sync uses (api/services/event_matching.py);
        # restricted to source='manual' since that's the only source this
        # public endpoint ever writes.
        existing_equivalent = find_equivalent_event(
            conn, data.athlete_id, data.event_date, data.start_time, data.event_type,
            data.event_name, "source = 'manual'",
        )
        if existing_equivalent:
            return existing_equivalent

        try:
            row = conn.execute(
                "INSERT INTO events (athlete_id, event_name, event_type, event_date, start_time, duration_hours, city, venue_name, address, latitude, longitude, intensity, activity_type, uid, source) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (data.athlete_id, data.event_name, data.event_type, data.event_date, data.start_time, data.duration_hours,
                 data.city, data.venue_name, data.address, data.latitude, data.longitude, intensity, data.activity_type, data.uid, data.source),
            ).fetchone()
            conn.commit()
        except psycopg.errors.UniqueViolation:
            # Partial unique index on (athlete_id, uid) tripped — this ICS event is
            # already on the schedule. Make the POST idempotent: return the existing
            # row, skip the window recompute. The client also pre-skips duplicates,
            # so this only catches races / direct re-POSTs.
            conn.rollback()
            existing = conn.execute(
                "SELECT * FROM events WHERE athlete_id = %s AND uid = %s",
                (data.athlete_id, data.uid),
            ).fetchone()
            if existing:
                return dict(existing)
            raise
        on_event_added_or_changed(data.athlete_id, data.event_date, conn)
        return dict(row)
    finally:
        conn.close()


@router.put("/{event_id}", response_model=EventResponse)
def update_event(event_id: int, data: EventUpdate, identity=Depends(require_session)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Event not found.")
        existing = dict(row)
        assert_owns_athlete(identity, existing["athlete_id"], conn)

        # Synced events are read-only — the club calendar is the source of truth, and
        # the 6-hourly sync would overwrite any local edit anyway. Manual events (the
        # default, source='manual' or legacy NULL) stay fully editable.
        if (existing.get("source") or "manual") != "manual":
            raise HTTPException(
                409, f"Cannot edit {existing['source']} synced events. Edit them in your club's calendar app.")

        new_name     = data.event_name     if data.event_name     is not None else existing["event_name"]
        new_type     = data.event_type     if data.event_type     is not None else existing["event_type"]
        new_date     = data.event_date     if data.event_date     is not None else existing["event_date"]
        new_start    = data.start_time     if data.start_time     is not None else existing["start_time"]
        new_dur      = data.duration_hours if data.duration_hours is not None else existing["duration_hours"]
        new_city     = data.city           if data.city           is not None else existing["city"]
        new_venue    = data.venue_name     if data.venue_name     is not None else existing["venue_name"]
        new_address  = data.address        if data.address        is not None else existing["address"]
        new_lat      = data.latitude       if data.latitude       is not None else existing["latitude"]
        new_lng      = data.longitude      if data.longitude      is not None else existing["longitude"]
        if data.intensity is not None:
            new_intensity = data.intensity
        elif existing["intensity"]:
            new_intensity = existing["intensity"]
        else:
            athlete = conn.execute(
                "SELECT competition_level FROM athletes WHERE id = %s", (existing["athlete_id"],)
            ).fetchone()
            level = athlete["competition_level"] if athlete else None
            new_intensity = derive_intensity(new_type, level)

        new_activity_type = data.activity_type if data.activity_type is not None else existing["activity_type"]

        conn.execute(
            "UPDATE events SET event_name=%s, event_type=%s, event_date=%s, start_time=%s, duration_hours=%s, "
            "city=%s, venue_name=%s, address=%s, latitude=%s, longitude=%s, intensity=%s, activity_type=%s WHERE id=%s",
            (new_name, new_type, new_date, new_start, new_dur,
             new_city, new_venue, new_address, new_lat, new_lng, new_intensity, new_activity_type, event_id),
        )
        conn.commit()
        updated = dict(conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone())
        on_event_added_or_changed(existing["athlete_id"], new_date, conn)
        # Also recalculate old date if date changed
        if data.event_date and data.event_date != existing["event_date"]:
            on_event_added_or_changed(existing["athlete_id"], existing["event_date"], conn)
        return updated
    finally:
        conn.close()


@router.patch("/{event_id}/activity-type", response_model=EventResponse)
def tag_activity_type(event_id: int, data: ActivityTypePatch, identity=Depends(require_session)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Event not found.")
        assert_owns_athlete(identity, dict(row)["athlete_id"], conn)
        conn.execute(
            "UPDATE events SET activity_type = %s WHERE id = %s",
            (data.activity_type, event_id),
        )
        conn.commit()
        ev = dict(conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone())
        on_event_added_or_changed(ev["athlete_id"], ev["event_date"], conn)
        return ev
    finally:
        conn.close()


@router.get("/athlete/{athlete_id}", response_model=List[EventResponse])
def get_athlete_events(athlete_id: int, date: str = None, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if date:
            rows = conn.execute(
                "SELECT * FROM events WHERE athlete_id = %s AND event_date = %s ORDER BY start_time",
                (athlete_id, date),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE athlete_id = %s ORDER BY event_date, start_time",
                (athlete_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, identity=Depends(require_session)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Event not found.")
        assert_owns_athlete(identity, dict(row)["athlete_id"], conn)
        return dict(row)
    finally:
        conn.close()


@router.delete("/{event_id}")
def delete_event(event_id: int, identity=Depends(require_session)):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE id = %s", (event_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Event not found.")
        ev = dict(row)
        assert_owns_athlete(identity, ev["athlete_id"], conn)
        # Synced events are read-only (see update_event) — deleting locally would just
        # let the next sync re-insert the event. Manual events remain deletable.
        if (ev.get("source") or "manual") != "manual":
            raise HTTPException(
                409, f"Cannot delete {ev['source']} synced events. Remove them in your club's calendar app.")
        conn.execute("DELETE FROM events WHERE id = %s", (event_id,))
        conn.commit()
        on_event_added_or_changed(ev["athlete_id"], ev["event_date"], conn)
        return {"message": "Event deleted.", "event_id": event_id}
    finally:
        conn.close()
