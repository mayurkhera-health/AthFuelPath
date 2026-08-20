import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_athlete, assert_owns_parent

router = APIRouter()

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").replace("\\n", "\n")
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CONTACT     = os.getenv("VAPID_CONTACT", "mailto:purvi@dietsandlife.com")


class PushSubscription(BaseModel):
    athlete_id: int
    endpoint: str
    p256dh: str
    auth: str


class ExpoTokenPayload(BaseModel):
    token: str
    platform: Optional[str] = None
    timezone: Optional[str] = None   # IANA tz, e.g. "America/Los_Angeles"
    athlete_id: Optional[int] = None
    parent_id: Optional[int] = None


@router.post("/expo-token")
def register_expo_token(data: ExpoTokenPayload, identity=Depends(require_session)):
    if not data.athlete_id and not data.parent_id:
        return {"message": "No profile id provided."}
    conn = get_conn()
    try:
        # Registering a token for a profile requires the caller's own session to
        # actually be that profile — otherwise anyone who knows/guesses an
        # athlete_id or parent_id could register their own device against it and
        # silently start receiving that family's push notifications.
        if data.athlete_id:
            assert_owns_athlete(identity, data.athlete_id, conn)
        if data.parent_id:
            assert_owns_parent(identity, data.parent_id)
        # A push token belongs to a DEVICE, not a person — on a shared device (one
        # family tablet/phone used by both a parent and an athlete), the parent's
        # registration and the athlete's registration carry the SAME token. Since
        # token is the unique key, an unconditional overwrite here would blank out
        # whichever id the other profile's registration didn't send (e.g. the
        # athlete's call sends athlete_id with no parent_id, wiping the parent_id
        # a prior registration had set) — silently killing that profile's push
        # notifications with no error surfaced anywhere. COALESCE keeps whichever
        # side the current call doesn't mention, so one token can carry both ids.
        conn.execute(
            """INSERT INTO expo_push_tokens (athlete_id, parent_id, token, platform, timezone)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT(token) DO UPDATE SET
               athlete_id=COALESCE(excluded.athlete_id, expo_push_tokens.athlete_id),
               parent_id=COALESCE(excluded.parent_id, expo_push_tokens.parent_id),
               platform=excluded.platform,
               timezone=excluded.timezone,
               updated_at=sqlite_now()""",
            (data.athlete_id, data.parent_id, data.token, data.platform, data.timezone),
        )
        # Prune stale tokens for this profile (older than 30 days, different token).
        # Prevents duplicate notifications when the same device gets a new token after
        # a reinstall — the old token stays in DB otherwise and every alert fires twice.
        if data.parent_id:
            conn.execute(
                """DELETE FROM expo_push_tokens
                   WHERE parent_id = %s AND token != %s
                   AND COALESCE(updated_at, created_at) < to_char((now() AT TIME ZONE 'UTC') - INTERVAL '30 days', 'YYYY-MM-DD HH24:MI:SS')""",
                (data.parent_id, data.token),
            )
        if data.athlete_id:
            conn.execute(
                """DELETE FROM expo_push_tokens
                   WHERE athlete_id = %s AND token != %s
                   AND COALESCE(updated_at, created_at) < to_char((now() AT TIME ZONE 'UTC') - INTERVAL '30 days', 'YYYY-MM-DD HH24:MI:SS')""",
                (data.athlete_id, data.token),
            )
        conn.commit()
        return {"message": "Token registered."}
    finally:
        conn.close()


class NotificationPrefs(BaseModel):
    remind_pregame_meal:  Optional[bool] = True
    remind_pregame_snack: Optional[bool] = True
    remind_meal_log:      Optional[bool] = True
    remind_hydration:     Optional[bool] = True


class FuelIQNotifPrefs(BaseModel):
    athlete_id:       int
    morning_enabled:  bool = True
    pregame_enabled:  bool = True


@router.patch("/fueliq-prefs")
def update_fueliq_notif_prefs(data: FuelIQNotifPrefs):
    """Upsert per-athlete Fuel IQ notification prefs. Called by the mobile
    settings screen whenever either toggle changes."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO fueliq_notification_prefs (athlete_id, morning_enabled, pregame_enabled)
               VALUES (%s, %s, %s)
               ON CONFLICT(athlete_id) DO UPDATE SET
               morning_enabled = excluded.morning_enabled,
               pregame_enabled = excluded.pregame_enabled,
               updated_at      = sqlite_now()""",
            (data.athlete_id, int(data.morning_enabled), int(data.pregame_enabled)),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


class NotificationPrefsUpdate(BaseModel):
    profile_type:        str   # "athlete" | "parent"
    profile_id:          int
    training_days:       bool = True
    game_days:           bool = True
    quiet_hours_enabled: bool = True
    quiet_start:         str = "22:00"  # "HH:MM"
    quiet_end:           str = "07:00"  # "HH:MM"


@router.patch("/prefs")
def update_notification_prefs(data: NotificationPrefsUpdate, identity=Depends(require_session)):
    """Upsert per-profile Training/Game Day + Quiet Hours prefs (Settings →
    Notifications / Quiet Hours). An athlete and their parent each set their
    own row — they're silencing their own phone independently. Read by
    notification_service.py's per-recipient gating in _notify_athlete."""
    if data.profile_type not in ("athlete", "parent"):
        raise HTTPException(400, "profile_type must be 'athlete' or 'parent'.")
    conn = get_conn()
    try:
        table = "athletes" if data.profile_type == "athlete" else "parents"
        exists = conn.execute(
            f"SELECT 1 FROM {table} WHERE id = %s", (data.profile_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(404, f"{data.profile_type.capitalize()} not found.")
        if data.profile_type == "athlete":
            assert_owns_athlete(identity, data.profile_id, conn)
        else:
            assert_owns_parent(identity, data.profile_id)
        conn.execute(
            """INSERT INTO notification_prefs
                   (profile_type, profile_id, training_days, game_days,
                    quiet_hours_enabled, quiet_start, quiet_end)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT(profile_type, profile_id) DO UPDATE SET
                   training_days       = excluded.training_days,
                   game_days           = excluded.game_days,
                   quiet_hours_enabled = excluded.quiet_hours_enabled,
                   quiet_start         = excluded.quiet_start,
                   quiet_end           = excluded.quiet_end,
                   updated_at          = sqlite_now()""",
            (data.profile_type, data.profile_id, int(data.training_days), int(data.game_days),
             int(data.quiet_hours_enabled), data.quiet_start, data.quiet_end),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/vapid-public-key")
def get_vapid_public_key():
    return {"publicKey": VAPID_PUBLIC_KEY}


@router.post("/subscribe")
def subscribe(data: PushSubscription):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO push_subscriptions (athlete_id, endpoint, p256dh, auth)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT(athlete_id, endpoint) DO UPDATE SET
               p256dh=excluded.p256dh, auth=excluded.auth""",
            (data.athlete_id, data.endpoint, data.p256dh, data.auth),
        )
        conn.commit()
        return {"message": "Subscribed to push notifications."}
    finally:
        conn.close()


@router.get("/{athlete_id}/prefs")
def get_prefs(athlete_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM push_subscriptions WHERE athlete_id = %s ORDER BY id DESC LIMIT 1",
            (athlete_id,),
        ).fetchone()
        if not row:
            return {"subscribed": False, "remind_pregame_meal": True, "remind_pregame_snack": True,
                    "remind_meal_log": True, "remind_hydration": True}
        r = dict(row)
        return {"subscribed": True, "remind_pregame_meal": bool(r["remind_pregame_meal"]),
                "remind_pregame_snack": bool(r["remind_pregame_snack"]),
                "remind_meal_log": bool(r["remind_meal_log"]),
                "remind_hydration": bool(r["remind_hydration"])}
    finally:
        conn.close()


@router.put("/{athlete_id}/prefs")
def update_prefs(athlete_id: int, prefs: NotificationPrefs):
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE push_subscriptions SET
               remind_pregame_meal=%s, remind_pregame_snack=%s,
               remind_meal_log=%s, remind_hydration=%s
               WHERE athlete_id=%s""",
            (prefs.remind_pregame_meal, prefs.remind_pregame_snack,
             prefs.remind_meal_log, prefs.remind_hydration, athlete_id),
        )
        conn.commit()
        return {"message": "Preferences updated."}
    finally:
        conn.close()


@router.delete("/{athlete_id}/unsubscribe")
def unsubscribe(athlete_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM push_subscriptions WHERE athlete_id = %s", (athlete_id,))
        conn.commit()
        return {"message": "Unsubscribed from push notifications."}
    finally:
        conn.close()
