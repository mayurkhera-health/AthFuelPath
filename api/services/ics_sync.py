"""
Recurring calendar sync — BYGA + PlayMetrics .ics feeds.

A background APScheduler job (`run_calendar_sync_tick`, registered in api/main.py)
fetches every athlete's stored .ics subscription URL(s) and reconciles the feed
into the `events` table: INSERT new games/practices, UPDATE ones whose time or
place changed, and DELETE future ones that vanished from the feed (a cancelled or
removed game). Every mutation calls `on_event_added_or_changed` so the fuel-window
engine regenerates that day's Today / Meal-Plan windows — exactly like the manual
POST/PUT/DELETE /events routes do.

Design mirrors the client-side importer (mobile utils/icsImport.ts) so a synced
event classifies identically to a hand-imported one, with two server-only guards:

  * "Past" is judged in each event's own TZID (Option 1A) with a 24h buffer, since
    a background job has no client timezone and Fly runs UTC.
  * The DELETE phase only removes FUTURE events (event_date >= cutoff) whose source
    matches the feed, and is skipped entirely when a fetch fails or the feed has no
    VEVENTs — so a transient/empty feed can never wipe the athlete's schedule, and
    manual events (source='manual') are never touched.
"""

import ipaddress
import logging
import socket
import threading
from datetime import datetime, timedelta, timezone, date
from urllib.parse import urlparse

import httpx
import psycopg
from icalendar import Calendar

from api.database import get_conn
from api.services.window_templates import on_event_added_or_changed
from api.services.nutrition_calc import derive_intensity
from api.services.event_matching import find_equivalent_event, acquire_reconciliation_lock, MatchStatus

logger = logging.getLogger(__name__)

# How far back an event may sit before it's "past". A full day comfortably covers
# any client-vs-UTC offset, so we never delete a today/yesterday event over tz skew.
_PAST_BUFFER = timedelta(hours=24)

_PLATFORMS = ("byga", "playmetrics")


# ─── URL + fetch ──────────────────────────────────────────────────────────────
def normalize_calendar_url(url: str) -> str:
    """webcal(s):// is just http(s) under the calendar scheme — normalize so httpx
    can fetch it. Mirrors normalizeCalendarUrl / the fetch-ics proxy."""
    u = (url or "").strip()
    if u.startswith("webcal://"):
        return "https://" + u[len("webcal://"):]
    if u.startswith("webcals://"):
        return "https://" + u[len("webcals://"):]
    return u


_MAX_REDIRECTS = 5


def _is_disallowed_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified)


def _is_public_host(host: str) -> bool:
    """SSRF guard — reject any host that is (or resolves to) a private/loopback/
    link-local/reserved IP (RFC 1918, 169.254.0.0/16 cloud-metadata range, ::1,
    etc). Real BYGA/PlayMetrics feeds resolve to public hosting and pass through
    untouched; this only blocks a submitted URL from reaching internal
    infrastructure.

    A URL host that's already a literal IP address (e.g. "10.0.0.5") is checked
    directly via ipaddress — deterministic, no network I/O. This matters
    because routing a literal IP through socket.getaddrinfo() instead depends
    on the host machine's resolver/VPN/proxy stack, which can behave
    inconsistently for private ranges (observed: getaddrinfo misclassifying
    RFC1918 literals as resolvable/"public" after other outbound network
    activity on some machines) — a real bypass risk this avoids entirely for
    the literal-IP case, not just a test artifact."""
    try:
        return not _is_disallowed_ip(ipaddress.ip_address(host))
    except ValueError:
        pass  # not a literal IP — a real hostname needing DNS resolution
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for _, _, _, _, sockaddr in infos:
        if _is_disallowed_ip(ipaddress.ip_address(sockaddr[0])):
            return False
    return True


def fetch_ics_text(url: str) -> str:
    """Fetch raw ICS text. Raises on network / HTTP error — callers treat any raise
    as a failed feed and SKIP the delete phase (never wipe on a transient failure).

    SSRF guard: redirects are followed manually (follow_redirects=False) with the
    host re-validated on every hop — a URL that starts out public can still 302 to
    an internal address, so trusting httpx's automatic redirect following would
    only check the first hop."""
    fetch_url = normalize_calendar_url(url)
    if not fetch_url.startswith("http"):
        raise ValueError(f"Invalid calendar URL: {url!r}")

    for _ in range(_MAX_REDIRECTS + 1):
        host = urlparse(fetch_url).hostname
        if not host or not _is_public_host(host):
            raise ValueError(f"Calendar URL host is not allowed: {host!r}")
        resp = httpx.get(fetch_url, timeout=15, headers={"User-Agent": "AthFuelPath/1.0"},
                         follow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                resp.raise_for_status()
            fetch_url = str(httpx.URL(fetch_url).join(location))
            continue
        resp.raise_for_status()
        return resp.text
    raise ValueError("Too many redirects while fetching calendar feed")


# ─── Parsing ──────────────────────────────────────────────────────────────────
def guess_event_type(summary: str) -> str:
    """Map a VEVENT summary to a AthFuelPath event_type. Kept in lockstep with
    guessEventType in mobile utils/icsImport.ts so client + server agree."""
    s = (summary or "").lower()
    if "game" in s or "match" in s:
        return "game"
    if "tournament" in s or "tourney" in s:
        return "tournament"
    if "rest" in s or "off" in s or "recovery" in s:
        return "rest"
    if "strength" in s or "gym" in s or "lift" in s:
        return "strength"
    return "practice"


def _is_cancelled(vevent, summary: str) -> bool:
    # PlayMetrics double-signals: STATUS:CANCELLED *and* a "CANCELED " summary
    # prefix. Check both (matches the TS /^cancell?ed\b/i check).
    status = str(vevent.get("status", "")).upper()
    if status == "CANCELLED":
        return True
    head = (summary or "").strip().lower()
    return head.startswith("cancelled") or head.startswith("canceled")


def _as_utc(dt) -> datetime:
    """Coerce a VEVENT datetime to an aware UTC datetime for past-comparison. A
    TZID-bearing dt is converted from its own zone (Option 1A); a floating/naive
    dt is assumed UTC (conservative — at worst imports a barely-past event)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _vevent_to_event(vevent, cutoff_utc: datetime) -> dict | None:
    """Convert one VEVENT to an event dict, or None if it should be skipped
    (malformed / all-day / cancelled / past). Skip order matches icsImport.ts.

    event_date / start_time use the event's OWN local wall clock (its TZID), which
    is how the app stores + reasons about schedule times — not a UTC conversion."""
    uid = str(vevent.get("uid") or "").strip()
    summary = str(vevent.get("summary") or "").strip() or "Event"
    dtstart = vevent.get("dtstart")
    if not uid or dtstart is None:
        return None

    start = dtstart.dt
    # All-day entries (date, not datetime) carry no usable start time for the
    # window engine — SUMMER BREAK / OFF WEEKEND. Treat as unsupported.
    if isinstance(start, date) and not isinstance(start, datetime):
        return None

    if _is_cancelled(vevent, summary):
        return None

    # Past check in the event's own zone, with a 24h buffer.
    dtend = vevent.get("dtend")
    end = dtend.dt if dtend is not None else start
    if isinstance(end, date) and not isinstance(end, datetime):
        end = start
    if _as_utc(end) < cutoff_utc:
        return None

    # Local wall-clock date/time from the event's TZID (aware) or as-written (naive).
    event_date = start.strftime("%Y-%m-%d")
    start_time = start.strftime("%H:%M")

    # Duration: prefer DTEND, clamp to the same 0.5–8h band the client uses.
    duration_hours = 1.5
    try:
        if dtend is not None and isinstance(end, datetime) and isinstance(start, datetime):
            diff_h = (end - start).total_seconds() / 3600.0
            if diff_h > 0:
                duration_hours = diff_h
    except Exception:
        pass
    duration_hours = max(0.5, min(8.0, round(duration_hours * 2) / 2))

    location = str(vevent.get("location") or "").strip()
    city = location.split(",")[0].strip() if location else None

    return {
        "uid": uid,
        "event_name": summary,
        "event_type": guess_event_type(summary),
        "event_date": event_date,
        "start_time": start_time,
        "duration_hours": duration_hours,
        "city": city,
        "venue_name": location or None,
    }


def parse_feed(ics_text: str, cutoff_utc: datetime) -> dict[str, dict]:
    """Parse ICS text → {uid: event_dict} of the FUTURE, non-cancelled, timed events
    the feed wants on the schedule. Raises if the text isn't a calendar (callers
    treat a raise as a failed feed → skip delete). Last-write-wins on duplicate UIDs
    within one feed."""
    if "BEGIN:VCALENDAR" not in ics_text:
        raise ValueError("Not an ICS calendar (no VCALENDAR).")
    cal = Calendar.from_ical(ics_text)
    desired: dict[str, dict] = {}
    for comp in cal.walk("VEVENT"):
        try:
            ev = _vevent_to_event(comp, cutoff_utc)
        except Exception:
            logger.debug("Skipping malformed VEVENT", exc_info=True)
            continue
        if ev:
            desired[ev["uid"]] = ev
    return desired


# ─── Reconcile ────────────────────────────────────────────────────────────────
_SYNC_FIELDS = ("event_name", "event_type", "event_date", "start_time",
                "duration_hours", "city", "venue_name")


def _needs_update(existing: dict, desired: dict) -> bool:
    for f in _SYNC_FIELDS:
        if (existing.get(f) or None) != (desired.get(f) or None):
            return True
    return False


def sync_platform(conn, athlete_id: int, platform: str, ics_url: str,
                  competition_level: str | None) -> dict:
    """Fetch + reconcile one athlete's feed for one platform. Returns a counts dict
    for logging. Never raises — a bad feed is logged and skipped so one athlete's
    broken link can't abort the whole tick."""
    counts = {"inserted": 0, "updated": 0, "deleted": 0, "feed": 0, "error": None, "inserted_events": [],
              "source_upgraded": 0, "ambiguous_skipped": 0}
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - _PAST_BUFFER
    cutoff_date = (now_utc - _PAST_BUFFER).strftime("%Y-%m-%d")

    # 1. Fetch + parse. ANY failure here → skip reconcile entirely (no deletes).
    try:
        ics_text = fetch_ics_text(ics_url)
        desired = parse_feed(ics_text, cutoff_utc)
    except Exception as exc:
        counts["error"] = str(exc)
        logger.warning("Calendar fetch/parse failed (athlete %s, %s): %s",
                       athlete_id, platform, exc)
        return counts
    counts["feed"] = len(desired)

    # 2. Existing synced rows for this athlete + platform.
    existing_rows = conn.execute(
        "SELECT * FROM events WHERE athlete_id = %s AND source = %s",
        (athlete_id, platform),
    ).fetchall()
    existing = {r["uid"]: dict(r) for r in existing_rows if r["uid"]}
    now_iso = now_utc.isoformat()
    affected_dates: set[str] = set()
    # uids of same-platform rows left alone this cycle because they were an
    # AMBIGUOUS match (2+ candidates, none adopted). Phase 4's delete sweep
    # below removes any `existing` row whose uid isn't in this cycle's feed —
    # without this guard, an ambiguous row's OLD uid (never claimed under the
    # feed's new uid, since we deliberately didn't adopt it) would look
    # "vanished from the feed" and get deleted, turning "left alone for
    # manual review" into silent data loss. Confirmed by
    # test_ambiguous_same_platform_duplicates_do_not_multiply_on_resync
    # failing without this guard.
    protected_uids: set[str] = set()

    # 3. INSERT + UPDATE.
    for uid, ev in desired.items():
        intensity = derive_intensity(ev["event_type"], competition_level)
        if uid not in existing:
            # BYGA (and some other providers) rotate their VEVENT UIDs on every
            # export — and may also edit the event NAME between exports (a
            # trailing division code or facility number appended mid-season,
            # confirmed in production) — so a UID-only lookup never finds a
            # previously-imported copy of the same event, including one
            # imported by an EARLIER sync of this same platform (its uid is
            # stale too). Fall back to the shared event-equivalence matcher
            # (api/services/event_matching.py — same rule create_event uses),
            # checked in two tiers:
            #   1. Same-platform rows first — this is the real steady-state case
            #      (adopting our OWN prior sync's row under its now-rotated uid
            #      and/or edited name), and must not be blocked by unrelated
            #      leftover manual imports.
            #   2. Only if no same-platform row matches, fall back to a manual
            #      import — never a *different* connected platform, to avoid
            #      merging two distinct feeds' events that happen to collide.
            # Ambiguous (>1 candidate) at either tier must NOT fall through to
            # INSERT — that would turn "2 duplicates already exist" into 3.
            # It must also not arbitrarily adopt one of them. Skip this event
            # for this cycle entirely (no insert, no update, existing rows
            # left exactly as they are) and count/log it for later manual
            # cleanup — see event_matching.MatchResult's own docstring for
            # why this is a 3-way outcome, not a bare found/not-found check.
            #
            # Concurrency guard (Issue 5): scope the lock to this exact
            # (athlete, date, time, type) reconciliation decision so a
            # concurrent create_event call (or another sync tick) for the
            # SAME logical event can't race past this check-then-write.
            acquire_reconciliation_lock(
                conn, athlete_id, ev["event_date"], ev["start_time"], ev["event_type"],
            )
            tier1 = find_equivalent_event(
                conn, athlete_id, ev["event_date"], ev["start_time"], ev["event_type"],
                ev["event_name"], "source = %s", (platform,),
            )
            if tier1.status == MatchStatus.AMBIGUOUS_MATCH:
                counts["ambiguous_skipped"] += 1
                protected_uids.update(r["uid"] for r in tier1.rows if r.get("uid"))
                continue
            matched_row = tier1.row
            if matched_row is None:
                tier2 = find_equivalent_event(
                    conn, athlete_id, ev["event_date"], ev["start_time"], ev["event_type"],
                    ev["event_name"], "source = 'manual'",
                )
                if tier2.status == MatchStatus.AMBIGUOUS_MATCH:
                    counts["ambiguous_skipped"] += 1
                    continue
                matched_row = tier2.row
            if matched_row:
                matched = matched_row
                logger.debug(
                    "Name+time match for uid %s → adopting existing event id=%s (was source=%s)",
                    uid, matched["id"], matched.get("source"),
                )
                cur = conn.execute(
                    "UPDATE events SET uid=%s, source=%s, event_name=%s, event_type=%s, "
                    "duration_hours=%s, city=%s, venue_name=%s, intensity=%s, synced_at=%s WHERE id=%s",
                    (uid, platform, ev["event_name"], ev["event_type"], ev["duration_hours"],
                     ev["city"], ev["venue_name"], intensity, now_iso, matched["id"]),
                )
                if cur.rowcount == 0:
                    logger.warning(
                        "Name+time fallback UPDATE matched id=%s but rowcount=0 "
                        "(concurrent delete?)", matched["id"],
                    )
                else:
                    # Register under the new uid so the delete phase won't remove it.
                    # If the adopted row already had an entry in `existing` under its
                    # OLD uid (true when adopting a prior same-platform row on UID
                    # rotation — matched.uid was loaded into `existing` at step 2),
                    # drop that stale entry too. Otherwise phase 4's "uid not in
                    # desired" delete sweep matches the old key and removes the row
                    # we just updated, out from under itself.
                    existing.pop(matched.get("uid"), None)
                    existing[uid] = {**matched, "uid": uid, "source": platform}
                    counts["updated"] += 1
                    affected_dates.add(ev["event_date"])
                    if matched.get("event_date") != ev["event_date"]:
                        affected_dates.add(matched["event_date"])
            else:
                try:
                    # SAVEPOINT-scoped: a UniqueViolation here must only undo
                    # THIS insert attempt, never the whole sync_platform()
                    # transaction. conn.transaction() nests as a real SQL
                    # SAVEPOINT when called inside an already-open transaction
                    # (which we always are here — conn.commit() only happens
                    # once, at the end of the full reconcile loop) — so on
                    # exception it rolls back to the savepoint and re-raises,
                    # leaving every earlier INSERT/UPDATE from this same call
                    # intact and still uncommitted, ready for the final
                    # conn.commit(). The old code called the OUTER
                    # conn.rollback() here, which discarded ALL of that prior
                    # work — confirmed in production (Nora/athlete 62,
                    # 2026-08-29 Marin FC duplicate) and reproduced locally
                    # (test_uid_collision_rollback_does_not_discard_earlier_rename).
                    with conn.transaction():
                        conn.execute(
                            "INSERT INTO events (athlete_id, event_name, event_type, event_date, "
                            "start_time, duration_hours, city, venue_name, intensity, uid, source, synced_at) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (athlete_id, ev["event_name"], ev["event_type"], ev["event_date"],
                             ev["start_time"], ev["duration_hours"], ev["city"], ev["venue_name"],
                             intensity, uid, platform, now_iso),
                        )
                    counts["inserted"] += 1
                    counts["inserted_events"].append({
                        "event_name": ev["event_name"],
                        "event_date": ev["event_date"],
                        "event_type": ev["event_type"],
                    })
                    affected_dates.add(ev["event_date"])
                except psycopg.errors.UniqueViolation:
                    # Partial unique index (athlete_id, uid) — uid conflict.
                    # If the existing row is source='manual' (user previously
                    # uploaded a file), upgrade it to the platform source so the
                    # 6-hour job owns it going forward. Otherwise leave as-is.
                    # The failed INSERT was already rolled back to its own
                    # savepoint above (not the outer transaction) — no
                    # conn.rollback() here, or every earlier mutation in this
                    # same sync_platform() call would be discarded with it.
                    logger.debug("Insert skipped for uid %s", uid, exc_info=True)
                    upgraded = conn.execute(
                        "UPDATE events SET source = %s, synced_at = %s "
                        "WHERE athlete_id = %s AND uid = %s AND source = 'manual'",
                        (platform, now_iso, athlete_id, uid),
                    ).rowcount
                    if upgraded:
                        counts["source_upgraded"] += 1
                        affected_dates.add(ev["event_date"])
        else:
            cur = existing[uid]
            if _needs_update(cur, ev):
                conn.execute(
                    "UPDATE events SET event_name=%s, event_type=%s, event_date=%s, start_time=%s, "
                    "duration_hours=%s, city=%s, venue_name=%s, intensity=%s, synced_at=%s WHERE id=%s",
                    (ev["event_name"], ev["event_type"], ev["event_date"], ev["start_time"],
                     ev["duration_hours"], ev["city"], ev["venue_name"], intensity, now_iso, cur["id"]),
                )
                counts["updated"] += 1
                affected_dates.add(ev["event_date"])
                if cur["event_date"] != ev["event_date"]:
                    affected_dates.add(cur["event_date"])  # recompute the vacated day too

    # 4. DELETE — future-only, source-scoped. A synced event that dropped out of the
    #    feed (cancelled / removed) and is dated today-or-later gets removed. Past
    #    events (< cutoff) are preserved as history; manual events are never here.
    for uid, cur in existing.items():
        if uid in protected_uids:
            continue
        if uid not in desired and (cur["event_date"] or "") >= cutoff_date:
            conn.execute("DELETE FROM events WHERE id = %s", (cur["id"],))
            counts["deleted"] += 1
            affected_dates.add(cur["event_date"])

    conn.commit()

    # 5. Regenerate fuel windows once per touched day (idempotent full recompute).
    for d in affected_dates:
        try:
            on_event_added_or_changed(athlete_id, d, conn)
        except Exception:
            conn.rollback()
            logger.warning("Window recompute failed (athlete %s, %s)", athlete_id, d, exc_info=True)
    conn.commit()

    if counts["inserted"] or counts["updated"] or counts["deleted"] or counts["ambiguous_skipped"]:
        logger.info("Calendar sync %s/%s: +%d ~%d -%d ambiguous_skipped=%d (feed=%d)", athlete_id, platform,
                    counts["inserted"], counts["updated"], counts["deleted"],
                    counts["ambiguous_skipped"], counts["feed"])
    return counts


def _send_new_events_email(conn, athlete_id: int, platform: str, new_events: list) -> None:
    """Best-effort: email the parent when the 6-hour sync finds new events."""
    try:
        from api.services.email_service import send_email
        from api.services.email_templates import calendar_new_events_email
        row = conn.execute(
            "SELECT a.first_name, p.email, p.full_name "
            "FROM athletes a JOIN parents p ON p.id = a.parent_id "
            "WHERE a.id = %s",
            (athlete_id,),
        ).fetchone()
        if not row or not row["email"]:
            return
        platform_label = "BYGA" if platform == "byga" else "PlayMetrics"
        subject, text_body, html_body = calendar_new_events_email(
            parent_name=row["full_name"],
            athlete_name=row["first_name"],
            platform_label=platform_label,
            new_events=new_events,
        )
        send_email(subject=subject, body=text_body, to=[row["email"]],
                   html=html_body, bcc=["mayurkhera@gmail.com"])
    except Exception:
        conn.rollback()
        logger.warning("Failed to send new-events email (athlete %s, %s)",
                       athlete_id, platform, exc_info=True)


def run_calendar_sync_tick() -> None:
    """APScheduler entrypoint — sync every athlete that has connected a feed. One DB
    connection for the whole tick (mirrors run_notification_tick)."""
    conn = get_conn()
    attempted = succeeded = 0
    try:
        rows = conn.execute(
            "SELECT id, competition_level, byga_ics_url, playmetrics_ics_url FROM athletes "
            "WHERE byga_ics_url IS NOT NULL OR playmetrics_ics_url IS NOT NULL"
        ).fetchall()
        logger.info("Calendar sync tick: %d athlete(s) with feeds", len(rows))
        for row in rows:
            urls = {"byga": row["byga_ics_url"], "playmetrics": row["playmetrics_ics_url"]}
            for platform in _PLATFORMS:
                if urls[platform]:
                    attempted += 1
                    try:
                        counts = sync_platform(conn, row["id"], platform, urls[platform], row["competition_level"])
                        if not counts.get("error"):
                            succeeded += 1
                            # Email 2: notify parent when new events are found.
                            if counts["inserted"] > 0:
                                _send_new_events_email(conn, row["id"], platform, counts["inserted_events"])
                    except Exception:
                        conn.rollback()
                        logger.exception("Calendar sync crashed (athlete %s, %s)", row["id"], platform)
    finally:
        conn.close()
        # Feed the System Health calendar_sync_systemic check (systemic = a whole-
        # provider outage). Best-effort; must not affect sync behavior.
        try:
            from api.services.health_service import record_calendar_sync_stats
            record_calendar_sync_stats(attempted, succeeded)
        except Exception:
            pass


# ── Startup catch-up (Option B) ──────────────────────────────────────────────
# In-memory APScheduler timers reset on every deploy/restart, so a mid-cycle restart
# otherwise pushes the next 6-h run up to 6 h past schedule and trips the 420-min
# calendar-sync alert. On startup we either run one catch-up (stale/initial) or
# re-anchor the interval's first run to last_success + 6h (fresh). Notifications
# (15-min cadence) is unaffected and untouched.

_CALSYNC_LOCK = threading.Lock()


def _with_calsync_lock(fn):
    """Wrap a job callable in a non-blocking skip-if-running lock so the startup
    catch-up and the 6-h interval can never execute concurrently (they share the same
    underlying tick). The lock sits OUTSIDE instrument_job, so a skipped trigger stamps
    no heartbeat."""
    def wrapper():
        if not _CALSYNC_LOCK.acquire(blocking=False):
            logger.info("calendar_sync already running — skipping this trigger")
            return
        try:
            fn()
        finally:
            _CALSYNC_LOCK.release()
    wrapper.__name__ = getattr(fn, "__name__", "calendar_sync") + "_locked"
    return wrapper


def build_calendar_sync_job():
    """The callable registered as the 6-h interval AND reused for the startup catch-up:
    instrument_job (stamps heartbeats) wrapped in the skip-if-running lock."""
    from api.services.health_service import instrument_job
    return _with_calsync_lock(instrument_job("calendar_sync", run_calendar_sync_tick))


def configure_calendar_sync_startup(scheduler) -> None:
    """Option B startup handling for calendar_sync ONLY. Call once, after the 6-h
    interval job is registered and the scheduler is started.

      • initial (no prior successful run): claim + run ONE immediate sync;
        log 'no prior run — running initial sync'.
      • stale (> 6 h since last success): claim + run ONE immediate catch-up.
      • fresh (<= 6 h): re-anchor the interval's FIRST run to last_success + 6h so a
        sub-cadence restart resumes the original schedule instead of restarting the
        6-h clock. Re-anchor is applied ONLY here — a past-dated next_run_time in the
        initial/stale branches would make APScheduler fire the interval immediately
        alongside the catch-up (a double run)."""
    from api.services import health_service as hs
    conn = get_conn()
    try:
        branch, mins, last_success = hs.calendar_sync_freshness(conn)

        if branch == "fresh":
            anchor = datetime.fromisoformat(last_success).replace(tzinfo=timezone.utc) + timedelta(hours=6)
            try:
                scheduler.modify_job("calendar_sync", next_run_time=anchor)
                logger.info("calendar_sync fresh (%.0fm ago) — next run anchored to "
                            "last_success + 6h (%s)", mins, anchor.isoformat())
            except Exception:
                logger.exception("calendar_sync: failed to re-anchor next_run_time — "
                                 "leaving default interval schedule")
            return

        # initial or stale → claim exactly one catch-up (multi-instance safe)
        if not hs.claim_calendar_sync_catchup(conn):
            logger.info("calendar_sync %s but a run was already claimed/in progress — skipping catch-up", branch)
            return

        scheduler.add_job(
            build_calendar_sync_job(), "date",
            run_date=datetime.now(timezone.utc),
            id="calendar_sync_catchup", replace_existing=True,
            max_instances=1, coalesce=True,
        )
        if branch == "initial":
            logger.info("calendar_sync: no prior run — running initial sync")
        else:
            logger.info("calendar_sync stale (%.0fm > %dm) — running catch-up now",
                        mins, hs.CALSYNC_CADENCE_MIN)
    finally:
        conn.close()
