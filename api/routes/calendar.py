"""
Calendar sync URLs — connect / inspect / disconnect BYGA + PlayMetrics .ics feeds.

Stores the subscription URL on the athlete row; the recurring job in
api/services/ics_sync.py does the actual fetch+reconcile every 6 hours. Saving a
URL also runs one immediate sync so the athlete's schedule fills in right away.

Mounted at prefix /api/athletes, so the routes are /{athlete_id}/calendar/...
Every route requires a session token that owns athlete_id (see session_auth.py).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from api.database import get_conn
from api.services import ics_sync
from api.services.session_auth import require_session, assert_owns_athlete

logger = logging.getLogger(__name__)
router = APIRouter()

_PLATFORMS = ("byga", "playmetrics")
_COLUMN = {"byga": "byga_ics_url", "playmetrics": "playmetrics_ics_url"}


class CalendarSyncRequest(BaseModel):
    platform: str
    ics_url: str

    @field_validator("platform")
    @classmethod
    def _platform(cls, v: str) -> str:
        if v not in _PLATFORMS:
            raise ValueError("platform must be 'byga' or 'playmetrics'")
        return v

    @field_validator("ics_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.startswith(("webcal://", "webcals://", "http://", "https://")):
            raise ValueError("ics_url must start with webcal:// or https://")
        return v


def _require_athlete(conn, athlete_id: int):
    row = conn.execute(
        "SELECT id, competition_level FROM athletes WHERE id = %s", (athlete_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, "Athlete not found.")
    return row


@router.post("/{athlete_id}/calendar/sync-url")
def save_sync_url(athlete_id: int, body: CalendarSyncRequest, identity=Depends(require_session)):
    """Validate the feed (fetch + parse), store the URL, and run one immediate sync.
    A feed that can't be fetched/parsed is rejected 400 so a bad link isn't saved."""
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        athlete = _require_athlete(conn, athlete_id)

        # Validate by actually fetching + parsing — same path the job uses.
        try:
            from datetime import datetime, timezone
            ics_text = ics_sync.fetch_ics_text(body.ics_url)
            ics_sync.parse_feed(ics_text, datetime.now(timezone.utc) - ics_sync._PAST_BUFFER)
        except Exception as exc:
            raise HTTPException(400, f"Couldn't read that calendar link: {exc}")

        conn.execute(
            f"UPDATE athletes SET {_COLUMN[body.platform]} = %s WHERE id = %s",
            (body.ics_url, athlete_id),
        )
        conn.commit()

        # Immediate first sync so events appear now, not in up to 6h. Best-effort.
        counts = ics_sync.sync_platform(
            conn, athlete_id, body.platform, body.ics_url, athlete["competition_level"]
        )

        # Email 1: confirm the first sync to the parent. Best-effort — a failed
        # email must not roll back the sync or return an error to the client.
        try:
            from api.services.email_service import send_email
            from api.services.email_templates import calendar_first_sync_email
            parent = conn.execute(
                "SELECT p.email, p.full_name, a.first_name "
                "FROM parents p JOIN athletes a ON a.parent_id = p.id "
                "WHERE a.id = %s",
                (athlete_id,),
            ).fetchone()
            if parent and parent["email"]:
                platform_label = "BYGA" if body.platform == "byga" else "PlayMetrics"
                subject, text_body, html_body = calendar_first_sync_email(
                    parent_name=parent["full_name"],
                    athlete_name=parent["first_name"],
                    platform_label=platform_label,
                    counts=counts,
                )
                send_email(subject=subject, body=text_body, to=[parent["email"]],
                           html=html_body, bcc=["mayurkhera@gmail.com"])
        except Exception:
            logger.warning("Failed to send first-sync email (athlete %s, %s)",
                           athlete_id, body.platform, exc_info=True)

        return {"ok": True, "platform": body.platform, "sync": counts}
    finally:
        conn.close()


@router.get("/{athlete_id}/calendar/sync-status")
def sync_status(athlete_id: int, identity=Depends(require_session)):
    """Per-platform connection state + synced-event count + last sync time (derived
    from the most recent synced_at across that platform's events)."""
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        athlete = conn.execute(
            "SELECT byga_ics_url, playmetrics_ics_url FROM athletes WHERE id = %s",
            (athlete_id,),
        ).fetchone()
        if not athlete:
            raise HTTPException(404, "Athlete not found.")

        out = {"athlete_id": athlete_id}
        for platform in _PLATFORMS:
            agg = conn.execute(
                "SELECT COUNT(*) AS n, MAX(synced_at) AS last FROM events "
                "WHERE athlete_id = %s AND source = %s",
                (athlete_id, platform),
            ).fetchone()
            out[platform] = {
                "url": athlete[_COLUMN[platform]],
                "connected": athlete[_COLUMN[platform]] is not None,
                "synced_event_count": agg["n"],
                "last_sync": agg["last"],
            }
        return JSONResponse(content=out, headers={"Cache-Control": "no-store"})
    finally:
        conn.close()


@router.delete("/{athlete_id}/calendar/sync-url")
def remove_sync_url(athlete_id: int, platform: str, identity=Depends(require_session)):
    """Disconnect a feed: clears the stored URL so syncing stops. Already-synced
    events are KEPT (removing a link shouldn't wipe the athlete's schedule)."""
    if platform not in _PLATFORMS:
        raise HTTPException(400, "platform must be 'byga' or 'playmetrics'")
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        _require_athlete(conn, athlete_id)
        conn.execute(
            f"UPDATE athletes SET {_COLUMN[platform]} = NULL WHERE id = %s", (athlete_id,)
        )
        conn.commit()
        return {"ok": True, "platform": platform, "message": "Sync disconnected. Existing events kept."}
    finally:
        conn.close()
