import { useEffect, useRef, useState } from "react";
import { adminFetch, AuthError } from "./adminApi";
import { C, FONT_DISPLAY } from "./theme";
import { Card, Button, Skeleton, EmptyState, ErrorRetry } from "./ui";

// Checks whose metric_value is a genuine response time (ms). Only these get a
// "latency" pill — we never fabricate a latency for checks that don't have one.
const LATENCY_CHECKS = new Set(["bedrock_ping", "bedrock_inference", "gmail_smtp"]);

// Friendly name + a one-line "what this watches" for each sensor, so the page
// makes sense to a non-engineer. Keyed by backend check_name.
const META = {
  bedrock_ping: { title: "AI service", blurb: "Connection to the AI behind coaching & blueprints" },
  gmail_smtp: { title: "Email delivery", blurb: "Can sign in to the mailbox that sends emails" },
  db_writable: { title: "Database", blurb: "App database accepts reads & writes" },
  disk_space: { title: "Storage", blurb: "Free space on the data volume" },
  scheduler_notifications: { title: "Reminder scheduler", blurb: "The 15-min job that sends fueling reminders" },
  scheduler_calendar_sync: { title: "Calendar sync job", blurb: "The 6-hour job that refreshes connected calendars" },
  calendar_sync_systemic: { title: "Calendar feeds", blurb: "BYGA / PlayMetrics feeds importing successfully" },
  expo_push: { title: "Push notifications", blurb: "Recent push sends to phones are landing" },
  bedrock_inference: { title: "AI responses", blurb: "The AI can generate a reply · checked once a day" },
};

// Drill-down runbook: what a red on this sensor means and the first thing to
// try, in founder language. Shown in the detail drawer.
const RUNBOOK = {
  bedrock_ping: {
    means: "The app can't reach AWS Bedrock, so coaching replies and blueprint generation will fail until it recovers.",
    firstTry: "Usually an AWS blip — re-run the check. If it stays red for 15+ min, check the AWS status page and the app's AWS credentials.",
  },
  gmail_smtp: {
    means: "Sign-in to the sending mailbox failed — onboarding summaries and alert emails won't go out.",
    firstTry: "Google occasionally rejects a login; re-run the check. If persistent, the Gmail app password may have been revoked — mint a new one.",
  },
  db_writable: {
    means: "The app database refused a write. Nothing can be saved — this is the most serious sensor.",
    firstTry: "Check Storage next (a full volume causes this). If storage is fine, restart the Fly machine.",
  },
  disk_space: {
    means: "The data volume is filling up. At 100% the database stops accepting writes.",
    firstTry: "Extend the Fly volume, or clear old logs/backups from /data.",
  },
  scheduler_notifications: {
    means: "The 15-minute reminder job hasn't ticked lately — fueling push reminders aren't being sent.",
    firstTry: "A deploy restarts the machine and pauses this briefly; it should recover within 15 min. If not, check the Fly logs for a crashed scheduler.",
  },
  scheduler_calendar_sync: {
    means: "The 6-hour calendar refresh hasn't run on time, so synced BYGA/PlayMetrics schedules may be out of date.",
    firstTry: "If the app deployed recently, the timer reset and it recovers on the next tick — check Last error below. An actual error there means the job crashed mid-run.",
  },
  calendar_sync_systemic: {
    means: "The sync job runs, but every connected feed failed on the last pass — often a provider-side change.",
    firstTry: "Open Last error / feed counts below. If all feeds fail with the same error, BYGA or PlayMetrics likely changed their feed format.",
  },
  expo_push: {
    means: "Recent push notifications are all failing to reach phones.",
    firstTry: "Check recent sends below — 'DeviceNotRegistered' on every row means stale tokens; other errors point at Expo's push service.",
  },
  bedrock_inference: {
    means: "The daily end-to-end AI probe (a real generation) failed even though the connection ping may be fine.",
    firstTry: "Re-run the check. If ping is green but this stays red, the configured model ID may no longer be available in this AWS region.",
  },
};

// Human-readable detail — reassuring copy for the not-yet-run (pending) states,
// which otherwise read like failures. Green/red details from the backend are
// already clear, so they pass through.
const PENDING_COPY = {
  scheduler_notifications: "Waiting for first run — within 15 min of a deploy",
  scheduler_calendar_sync: "Waiting for first run — within 6 hours",
  calendar_sync_systemic: "No connected calendars to check yet",
  expo_push: "No push notifications sent recently",
  bedrock_inference: "Runs automatically once a day (09:00 UTC)",
};

function humanDetail(c) {
  if (c.status === "unknown") return PENDING_COPY[c.check_name] || "Waiting for first check";
  return c.detail || "—";
}

// Status → chip. Disk gets an amber "Watch" at ≥70% even while technically green.
function statusChip(c) {
  if (c.status === "red") return { label: "Down", fg: C.danger, bg: C.dangerBg, border: C.dangerBorder, dot: C.danger };
  if (c.check_name === "disk_space" && c.status === "green" && (c.metric_value ?? 0) >= 70)
    return { label: "Watch", fg: "#9a6a1e", bg: C.warmLight, border: "#f0d9a8", dot: C.warm };
  if (c.status === "green") return { label: "Healthy", fg: C.brand, bg: C.brandGhost, border: C.brandLight, dot: C.brandMid };
  return { label: "Pending", fg: C.text3, bg: C.surface2, border: C.border, dot: C.text3 };
}

// Card tone by chip label: a 4px status-color top strip + ultra-light surface
// ("Infrastructure Pulse" look). Pending stays neutral so it never reads alarming.
function cardTone(label) {
  if (label === "Down") return { accent: C.danger, bg: C.dangerBg };
  if (label === "Watch") return { accent: C.warm, bg: C.warmLight };
  if (label === "Healthy") return { accent: C.brandMid, bg: C.brandGhost };
  return { accent: C.border2, bg: C.surface };
}

// Severity pill for a log row's resulting status (spec's pill-style badges).
function severityPill(toStatus) {
  if (toStatus === "red") return { label: "Critical", fg: "#991b1b", bg: C.dangerBg, border: C.dangerBorder };
  if (toStatus === "green") return { label: "Resolved", fg: C.brand, bg: C.brandGhost, border: C.brandLight };
  return { label: "Pending", fg: C.text3, bg: C.surface2, border: C.border };
}

function parseUtc(iso) {
  if (!iso) return null;
  let s = iso.replace(" ", "T");
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s)) s += "Z";
  const d = new Date(s);
  return isNaN(d) ? null : d;
}
function timeAgo(iso) {
  const d = parseUtc(iso);
  if (!d) return "—";
  const secs = Math.floor((Date.now() - d.getTime()) / 1000);
  if (secs < 60) return "just now";
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
function fmtWhen(iso) {
  const d = parseUtc(iso);
  if (!d) return "—";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
// "443 min — goes red above 420 min" from the check row + threshold info.
function thresholdLine(check, threshold) {
  if (!threshold || check.metric_value == null) return null;
  const v = Math.round(check.metric_value * 10) / 10;
  return `${v}${threshold.unit === "%" ? "%" : ` ${threshold.unit}`} — goes red above ${threshold.red_above}${threshold.unit === "%" ? "%" : ` ${threshold.unit}`} (${threshold.metric})`;
}

// Overall reads from the founder's POV: is anything actually broken? Pending
// checks are informational, not a problem — they never turn the banner red.
function overallMeta(checks) {
  const red = checks.filter((c) => c.status === "red").length;
  const pending = checks.filter((c) => c.status === "unknown").length;
  if (red > 0) return { color: C.danger, label: `${red} ${red === 1 ? "issue needs" : "issues need"} attention` };
  if (pending > 0) return { color: C.brandMid, label: `All healthy · ${pending} still checking in` };
  return { color: C.brandMid, label: "All systems healthy" };
}

function Dot({ color, size = 11 }) {
  return <span style={{ display: "inline-block", width: size, height: size, borderRadius: "50%", background: color, flexShrink: 0 }} />;
}

// A labelled row inside the drawer's status/evidence sections.
function FactRow({ label, children, tone }) {
  return (
    <div style={{ display: "flex", gap: 10, padding: "7px 0", borderBottom: `1px solid ${C.border}`, alignItems: "baseline" }}>
      <span style={{ font: `600 12px ${FONT_DISPLAY}`, color: C.text3, minWidth: 108, flexShrink: 0 }}>{label}</span>
      <span style={{ font: `500 13px ${FONT_DISPLAY}`, color: tone || C.text1, wordBreak: "break-word" }}>{children}</span>
    </div>
  );
}

function SectionTitle({ children }) {
  return <div style={{ font: `800 12px ${FONT_DISPLAY}`, color: C.text3, letterSpacing: "0.06em", textTransform: "uppercase", margin: "18px 0 4px" }}>{children}</div>;
}

// Right-side drill-down drawer for one sensor. Fetches its own detail payload;
// onSnapshot lifts the refreshed grid up after a single-check re-run.
function SensorDrawer({ name, chip, onClose, onSnapshot, onLoggedOut }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [rerunning, setRerunning] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => {
    let alive = true;
    setDetail(null); setError("");
    adminFetch(`/health/checks/${name}`)
      .then((d) => { if (alive) setDetail(d); })
      .catch((err) => {
        if (err instanceof AuthError) return onLoggedOut();
        if (alive) setError(err.message);
      });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); clearInterval(timerRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function rerun() {
    if (rerunning || cooldown > 0) return;
    setRerunning(true);
    try {
      const snap = await adminFetch(`/health/run?check_name=${name}`, { method: "POST" });
      onSnapshot(snap);
      const d = await adminFetch(`/health/checks/${name}`);
      setDetail(d);
      setCooldown(60);
      timerRef.current = setInterval(() => {
        setCooldown((n) => { if (n <= 1) { clearInterval(timerRef.current); return 0; } return n - 1; });
      }, 1000);
    } catch (err) {
      if (err instanceof AuthError) return onLoggedOut();
      setError(err.message);
    } finally {
      setRerunning(false);
    }
  }

  const meta = META[name] || { title: name, blurb: "" };
  const rb = RUNBOOK[name];
  const check = detail?.check;
  const ev = detail?.evidence;
  const tl = check ? thresholdLine(check, detail.threshold) : null;

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,0.35)", zIndex: 60 }} />
      <div role="dialog" aria-label={`${meta.title} details`} style={{
        position: "fixed", top: 0, right: 0, bottom: 0, zIndex: 61,
        width: "min(440px, 100vw)", background: C.surface, boxShadow: C.shadowMd,
        overflowY: "auto", padding: "20px 22px 28px",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
          <div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ font: `800 19px ${FONT_DISPLAY}`, color: C.text1 }}>{meta.title}</span>
              {chip && (
                <span style={{
                  display: "inline-flex", gap: 5, alignItems: "center",
                  font: `700 11px ${FONT_DISPLAY}`, color: chip.fg, background: chip.bg,
                  border: `1px solid ${chip.border}`, borderRadius: 999, padding: "2px 9px",
                }}>
                  <Dot color={chip.dot} size={7} /> {chip.label}
                </span>
              )}
            </div>
            <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginTop: 3 }}>{meta.blurb}</div>
          </div>
          <button onClick={onClose} aria-label="Close" style={{
            border: "none", background: C.surface2, color: C.text2, borderRadius: 8,
            width: 30, height: 30, cursor: "pointer", font: `700 15px ${FONT_DISPLAY}`, flexShrink: 0,
          }}>×</button>
        </div>

        {error && <div style={{ marginTop: 16, font: `500 13px ${FONT_DISPLAY}`, color: C.danger }}>{error}</div>}
        {!detail && !error && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 18 }}>
            <Skeleton height={90} /><Skeleton height={140} /><Skeleton height={90} />
          </div>
        )}

        {detail && check && (
          <>
            <SectionTitle>Status</SectionTitle>
            <FactRow label="Latest reading" tone={check.status === "red" ? C.danger : undefined}>{humanDetail(check)}</FactRow>
            {tl && <FactRow label="Metric">{tl}</FactRow>}
            {check.status === "red" && check.last_red_at && <FactRow label="Down since" tone={C.danger}>{fmtWhen(check.last_red_at)} · {timeAgo(check.last_red_at)}</FactRow>}
            <FactRow label="Last healthy">{check.last_green_at ? `${fmtWhen(check.last_green_at)} · ${timeAgo(check.last_green_at)}` : "never seen green"}</FactRow>
            {check.last_alerted_at && <FactRow label="Last alert sent">{fmtWhen(check.last_alerted_at)} · {timeAgo(check.last_alerted_at)}</FactRow>}
            <FactRow label="Last checked">{check.last_checked_at ? `${fmtWhen(check.last_checked_at)} · ${timeAgo(check.last_checked_at)}` : "—"}</FactRow>

            {ev && ev.kind === "heartbeat" && (
              <>
                <SectionTitle>Job heartbeat</SectionTitle>
                <FactRow label="Last run">{ev.last_run_at ? `${fmtWhen(ev.last_run_at)} · ${timeAgo(ev.last_run_at)}` : "no run recorded"}</FactRow>
                <FactRow label="Last success">{ev.last_success_at ? `${fmtWhen(ev.last_success_at)} · ${timeAgo(ev.last_success_at)}` : "no success recorded"}</FactRow>
                <FactRow label="Last error" tone={ev.last_error ? C.danger : undefined}>
                  {ev.last_error ? <code style={{ font: "500 12px ui-monospace, monospace" }}>{ev.last_error}</code> : "none recorded — a clean stall, not a crash"}
                </FactRow>
                {ev.meta && ev.meta.attempted != null && (
                  <FactRow label="Last sync pass">{ev.meta.succeeded ?? 0}/{ev.meta.attempted} feeds succeeded</FactRow>
                )}
                {ev.feeds_connected != null && <FactRow label="Connected feeds">{ev.feeds_connected}</FactRow>}
              </>
            )}

            {ev && ev.kind === "push_log" && (
              <>
                <SectionTitle>Recent sends</SectionTitle>
                {ev.sends.length === 0 ? (
                  <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text3, padding: "8px 0" }}>No pushes sent yet.</div>
                ) : ev.sends.map((s2, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "baseline", padding: "6px 0", borderBottom: `1px solid ${C.border}` }}>
                    <Dot color={s2.success ? C.brandMid : C.danger} size={8} />
                    <span style={{ font: `500 12px ${FONT_DISPLAY}`, color: C.text2, flex: 1, wordBreak: "break-word" }}>{s2.detail || (s2.success ? "delivered" : "failed")}</span>
                    <span style={{ font: `500 11px ${FONT_DISPLAY}`, color: C.text3, flexShrink: 0 }}>{timeAgo(s2.created_at)}</span>
                  </div>
                ))}
              </>
            )}

            <SectionTitle>History</SectionTitle>
            {detail.incidents.length === 0 ? (
              <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text3, padding: "8px 0" }}>No status changes recorded for this sensor.</div>
            ) : detail.incidents.map((i) => {
              const label = (s2) => s2 === "red" ? "Down" : s2 === "green" ? "Healthy" : "Pending";
              const col = (s2) => s2 === "red" ? C.danger : s2 === "green" ? C.brandMid : C.text3;
              return (
                <div key={i.id} style={{ padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", font: `600 12px ${FONT_DISPLAY}`, color: C.text2 }}>
                    <Dot color={col(i.from_status)} size={8} /> {label(i.from_status)}
                    <span style={{ color: C.text3 }}>→</span>
                    <Dot color={col(i.to_status)} size={8} /> {label(i.to_status)}
                    <span style={{ marginLeft: "auto", color: C.text3, fontWeight: 500, fontSize: 11 }}>{fmtWhen(i.created_at)}</span>
                  </div>
                  {i.detail && <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginTop: 2 }}>{i.detail}</div>}
                </div>
              );
            })}

            {rb && (
              <>
                <SectionTitle>What this means</SectionTitle>
                <div style={{ font: `400 13px ${FONT_DISPLAY}`, color: C.text2, lineHeight: 1.5 }}>{rb.means}</div>
                <SectionTitle>First thing to try</SectionTitle>
                <div style={{ font: `400 13px ${FONT_DISPLAY}`, color: C.text2, lineHeight: 1.5 }}>{rb.firstTry}</div>
              </>
            )}

            <div style={{ marginTop: 22 }}>
              <Button onClick={rerun} disabled={rerunning || cooldown > 0}>
                {rerunning ? "Re-running…" : cooldown > 0 ? `Re-run this check (${cooldown}s)` : "Re-run this check"}
              </Button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

export default function AdminHealth({ onLoggedOut }) {
  const [data, setData] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [showAllLogs, setShowAllLogs] = useState(false);
  const [selected, setSelected] = useState(null);   // check_name whose drawer is open
  const timerRef = useRef(null);

  useEffect(() => {
    load();
    return () => clearInterval(timerRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [snap, inc] = await Promise.all([
        adminFetch("/health"),
        adminFetch("/health/incidents?limit=50"),
      ]);
      setData(snap);
      setIncidents(inc.items || []);
    } catch (err) {
      if (err instanceof AuthError) return onLoggedOut();
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function checkNow() {
    if (running || cooldown > 0) return;
    setRunning(true);
    try {
      const snap = await adminFetch("/health/run", { method: "POST" });
      setData(snap);
      const inc = await adminFetch("/health/incidents?limit=50");
      setIncidents(inc.items || []);
      setCooldown(60);
      timerRef.current = setInterval(() => {
        setCooldown((n) => { if (n <= 1) { clearInterval(timerRef.current); return 0; } return n - 1; });
      }, 1000);
    } catch (err) {
      if (err instanceof AuthError) return onLoggedOut();
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  if (loading) return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Skeleton height={28} width={200} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 12 }}>
        {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} height={110} />)}
      </div>
    </div>
  );
  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (!data) return null;

  const om = overallMeta(data.checks);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, flexWrap: "wrap", gap: 12 }}>
        <h1 style={{ font: `800 24px ${FONT_DISPLAY}`, color: C.text1, margin: 0 }}>System Health</h1>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <span style={{ display: "inline-flex", gap: 8, alignItems: "center", font: `700 14px ${FONT_DISPLAY}`, color: om.color }}>
            <Dot color={om.color} /> {om.label}
          </span>
          <Button variant="ghost" onClick={checkNow} disabled={running || cooldown > 0}>
            {running ? "Checking…" : cooldown > 0 ? `Check now (${cooldown}s)` : "Check now"}
          </Button>
        </div>
      </div>
      <p style={{ font: `400 13px ${FONT_DISPLAY}`, color: C.text3, margin: "0 0 18px" }}>
        Live status of the services AthFuelPath depends on. “Pending” checks simply haven’t run since the last deploy — not a problem.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 14, marginBottom: 24 }}>
        {data.checks.map((c) => {
          const meta = META[c.check_name] || { title: c.check_name, blurb: "" };
          const chip = statusChip(c);
          const tone = cardTone(chip.label);
          const showLatency = LATENCY_CHECKS.has(c.check_name) && c.status === "green" && c.metric_value != null;
          return (
            <div key={c.check_name} role="button" tabIndex={0} aria-label={`Open ${meta.title} details`}
              onClick={() => setSelected(c.check_name)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(c.check_name); } }}
              style={{ cursor: "pointer" }}>
            <Card style={{
              padding: 16, borderColor: C.border, background: tone.bg,
              borderTop: `4px solid ${tone.accent}`, height: "100%",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                <span style={{ font: `800 15px ${FONT_DISPLAY}`, color: C.text1 }}>{meta.title}</span>
                <span style={{
                  display: "inline-flex", gap: 5, alignItems: "center", flexShrink: 0,
                  font: `700 11px ${FONT_DISPLAY}`, color: chip.fg, background: chip.bg,
                  border: `1px solid ${chip.border}`, borderRadius: 999, padding: "2px 9px",
                }}>
                  <Dot color={chip.dot} size={7} /> {chip.label}
                </span>
              </div>
              <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginTop: 4, minHeight: 30 }}>
                {meta.blurb}
              </div>
              {showLatency && (
                <div style={{
                  display: "inline-flex", gap: 5, alignItems: "center", marginTop: 8,
                  font: `700 11px ${FONT_DISPLAY}`, color: C.text2, background: C.surface,
                  border: `1px solid ${C.border}`, borderRadius: 8, padding: "3px 8px",
                }}>
                  ⚡ {Math.round(c.metric_value)} ms
                  <span style={{ color: C.text3, fontWeight: 500 }}>response</span>
                </div>
              )}
              <div style={{ font: `600 13px ${FONT_DISPLAY}`, color: C.text2, marginTop: 8, minHeight: 18 }}>
                {humanDetail(c)}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
                <span style={{ font: `500 11px ${FONT_DISPLAY}`, color: C.text3 }}>
                  Last checked {c.last_checked_at ? timeAgo(c.last_checked_at) : "—"}
                </span>
                <span style={{ font: `700 11px ${FONT_DISPLAY}`, color: C.brand }}>Details →</span>
              </div>
            </Card>
            </div>
          );
        })}
      </div>

      <h2 style={{ font: `800 18px ${FONT_DISPLAY}`, color: C.text1, margin: "0 0 4px" }}>Recent changes</h2>
      <p style={{ font: `400 13px ${FONT_DISPLAY}`, color: C.text3, margin: "0 0 12px" }}>
        Every time a sensor changes state it’s logged here.
      </p>
      <Card style={{ padding: 0 }}>
        {incidents.length === 0 ? (
          <EmptyState title="Nothing to report" subtitle="Status changes will show up here." />
        ) : (
          (showAllLogs ? incidents : incidents.slice(0, 15)).map((i) => {
            const meta = META[i.check_name] || { title: i.check_name };
            const label = (s) => s === "red" ? "Down" : s === "green" ? "Healthy" : "Pending";
            const col = (s) => s === "red" ? C.danger : s === "green" ? C.brandMid : C.text3;
            const sev = severityPill(i.to_status);
            return (
              <div key={i.id} style={{
                display: "flex", gap: 12, alignItems: "center", padding: "11px 16px",
                borderBottom: `1px solid ${C.border}`, font: `500 13px ${FONT_DISPLAY}`, color: C.text1, flexWrap: "wrap",
              }}>
                <span style={{ color: C.text3, minWidth: 92, fontSize: 12 }}>
                  {(i.created_at || "").slice(5, 16).replace("T", " ")}
                </span>
                <span style={{ minWidth: 150, fontWeight: 700 }}>{meta.title}</span>
                <span style={{ display: "inline-flex", gap: 6, alignItems: "center", color: C.text2, fontSize: 12 }}>
                  <Dot color={col(i.from_status)} size={8} /> {label(i.from_status)}
                  <span style={{ color: C.text3 }}>→</span>
                  <Dot color={col(i.to_status)} size={8} /> {label(i.to_status)}
                </span>
                <span style={{ color: C.text3, flex: 1, minWidth: 140, fontSize: 12 }}>{i.detail}</span>
                <span style={{
                  flexShrink: 0, font: `700 10px ${FONT_DISPLAY}`, letterSpacing: "0.04em", textTransform: "uppercase",
                  color: sev.fg, background: sev.bg, border: `1px solid ${sev.border}`, borderRadius: 999, padding: "2px 9px",
                }}>{sev.label}</span>
              </div>
            );
          })
        )}
        {incidents.length > 15 && (
          <button onClick={() => setShowAllLogs((v) => !v)} style={{
            display: "block", width: "100%", cursor: "pointer", background: "transparent",
            border: "none", borderTop: `1px solid ${C.border}`, padding: "12px",
            font: `700 13px ${FONT_DISPLAY}`, color: C.brand,
          }}>
            {showAllLogs ? "Show less" : `Load more logs (${incidents.length - 15} more)`}
          </button>
        )}
      </Card>

      {selected && (
        <SensorDrawer
          name={selected}
          chip={(() => { const c = data.checks.find((x) => x.check_name === selected); return c ? statusChip(c) : null; })()}
          onClose={() => setSelected(null)}
          onSnapshot={(snap) => setData(snap)}
          onLoggedOut={onLoggedOut}
        />
      )}
    </div>
  );
}
