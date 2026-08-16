import { useEffect, useState } from "react";
import { adminFetch, AuthError } from "./adminApi";
import { C, FONT_DISPLAY } from "./theme";
import { Card, Button, StatCard, LineChart, FunnelBars, PieChart, Skeleton, ErrorRetry } from "./ui";

export default function AdminAnalytics({ onLoggedOut }) {
  const [overview, setOverview] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [events, setEvents] = useState(null);
  const [retention, setRetention] = useState(null);
  const [activity, setActivity] = useState(null);
  const [activityRefreshing, setActivityRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    load(false);
    loadActivity(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load(force) {
    force ? setRefreshing(true) : setLoading(true);
    setError("");
    try {
      const f = force ? "?force=true" : "";
      const [ov, fn, ev, rt] = await Promise.all([
        adminFetch(`/analytics/overview${force ? "?force=true" : ""}`),
        adminFetch(`/analytics/funnel`),
        adminFetch(`/analytics/events${f}`),
        adminFetch(`/analytics/retention${f}`),
      ]);
      setOverview(ov); setFunnel(fn); setEvents(ev); setRetention(rt);
    } catch (err) {
      if (err instanceof AuthError) return onLoggedOut();
      setError(err.message);
    } finally { setLoading(false); setRefreshing(false); }
  }

  // The activity feed refreshes on its own (short-cached, "live") so its Refresh
  // never reloads the whole dashboard. No polling — manual refresh only.
  async function loadActivity(force) {
    if (force) setActivityRefreshing(true);
    try {
      const a = await adminFetch(`/analytics/activity?limit=20${force ? "&force=true" : ""}`);
      setActivity(a);
    } catch (err) {
      if (err instanceof AuthError) return onLoggedOut();
      setActivity({ error: true });
    } finally { setActivityRefreshing(false); }
  }

  if (loading) return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Skeleton height={28} width={160} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 }}>
        {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={96} />)}
      </div>
      <Skeleton height={220} /><Skeleton height={200} />
    </div>
  );
  if (error) return <ErrorRetry message={error} onRetry={() => load(false)} />;

  const c = overview.cards;
  const asOf = (overview.as_of || "").slice(11, 16);
  const ph = overview.posthog_status || { configured: overview.posthog_available, available: overview.posthog_available };
  // Note only when the PostHog Query API isn't usable (unconfigured or erroring).
  // An empty-but-working PostHog still counts as available (cards show "no data").
  const phNote = !ph.available;
  const phNoteText = ph.configured
    ? "PostHog Query API is unavailable right now (check the Personal API Key) — showing database-backed metrics."
    : "PostHog not connected — showing database-backed metrics. Signup, funnel, and health cards are fully available.";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <h1 style={{ font: `800 24px ${FONT_DISPLAY}`, color: C.text1, margin: 0 }}>Analytics</h1>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text3 }}>as of {asOf} UTC</span>
          <Button variant="ghost" onClick={() => load(true)} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      <FounderSummary overview={overview} funnel={funnel} />

      {phNote && (
        <div style={{
          font: `500 13px ${FONT_DISPLAY}`, color: C.text2, background: C.warmLight,
          border: `1px solid #f0d9a8`, borderRadius: 10, padding: "8px 14px", marginBottom: 16,
        }}>{phNoteText}</div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 16 }}>
        <StatCard label={`Signups (${c.signups.window_days}d)`} value={c.signups.value} sub="new families" />
        <StatCard label="Active users (7d)" value={c.active_users_7d.value} sub="athletes with activity" />
        <StatCard label="Families" value={c.families_total.value} sub="total" />
        <StatCard label="Sync adoption" value={`${c.sync_adoption.percent}%`}
          sub={`${c.sync_adoption.connected}/${c.sync_adoption.total} athletes`} />
      </div>

      {/* Charts as a responsive dashboard grid — 2–3 across on wide screens,
          single column on phones (min() keeps the 440px track from overflowing). */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(440px,100%),1fr))", gap: 16, alignItems: "start" }}>
        <RecentActivity activity={activity} onRefresh={() => loadActivity(true)} refreshing={activityRefreshing} />

        <CalendarPlatform data={overview.calendar_platform} />

        <Card>
          <SectionTitle>Signups over time ({c.signups.window_days}d)</SectionTitle>
          <LineChart points={overview.signups_over_time.points} />
        </Card>

        <Card>
          <SectionTitle>Activation funnel <Src>DB</Src></SectionTitle>
          <FunnelBars steps={funnel.steps} />
          <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginTop: 10 }}>{funnel.note}</div>
        </Card>

        <Card>
          <SectionTitle>Weekly active users <Src>{retention.source === "posthog" ? "PostHog" : "DB (WAU)"}</Src></SectionTitle>
          <Retention retention={retention} />
        </Card>

        <Card>
          <SectionTitle>Top events (30d) <Src>PostHog</Src></SectionTitle>
          <TopEvents events={events} />
        </Card>

        <AppHealth appHealth={overview.app_health} onLoggedOut={onLoggedOut} />
      </div>
    </div>
  );
}

// Plain-language, jargon-free headline for a non-technical team member checking
// hourly. All values come from our own database (always available), so it never
// shows "no data" or depends on PostHog. Detailed charts live below for the deep view.
function FounderSummary({ overview, funnel }) {
  const c = overview.cards;
  const families = c.families_total.value;
  const active = c.active_users_7d.value;
  const bugs = overview.app_health.problem_reports_7d;
  const ideas = overview.app_health.feature_ideas_7d;
  const step = (label) => funnel?.steps?.find((s) => s.label === label)?.value;
  const connected = step("Connected calendar") ?? c.sync_adoption.connected;
  const base = step("Signed up") ?? families;
  const asOf = (overview.as_of || "").slice(11, 16);

  const rows = [
    { ok: true, text: `${families} ${families === 1 ? "family" : "families"} using AthFuelPath` },
    {
      ok: active > 0,
      text: active > 0 ? `${active} ${active === 1 ? "athlete" : "athletes"} active this week` : "No athletes active this week",
    },
    {
      ok: base > 0 && connected * 2 >= base,
      text: `${connected} of ${base} ${base === 1 ? "family has" : "families have"} added their schedule`,
    },
    {
      ok: bugs === 0,
      text: bugs > 0 ? `${bugs} ${bugs === 1 ? "problem" : "problems"} reported this week` : "No problems reported this week",
    },
    {
      ok: true,
      text: ideas > 0 ? `${ideas} new ${ideas === 1 ? "idea" : "ideas"} this week` : "No new ideas this week",
    },
  ];

  return (
    <Card style={{ marginBottom: 18, background: C.brandGhost, borderColor: C.brandLight }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
        <span style={{ font: `800 18px ${FONT_DISPLAY}`, color: C.text1 }}>At a glance</span>
        <span style={{ font: `500 12px ${FONT_DISPLAY}`, color: C.text3 }}>updated {asOf} UTC</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
        {rows.map((r, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 11, font: `600 15px ${FONT_DISPLAY}`, color: C.text1 }}>
            <span style={{ fontSize: 15, width: 20, textAlign: "center" }}>{r.ok ? "🟢" : "⚠️"}</span>
            <span>{r.text}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// Plain-language labels for the activity feed (canonical event → "did what").
const EVENT_LABELS = {
  signup_completed: "signed up",
  athlete_created: "added an athlete",
  calendar_connected: "connected calendar",
  meal_plan_viewed: "viewed meal plan",
  event_added_manual: "added an event",
  problem_reported: "reported a problem",
  feature_idea_submitted: "suggested a feature",
};

// Relative time — small helper, no date library.
function relTime(iso) {
  if (!iso) return "";
  let s = String(iso).replace(" ", "T");
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s)) s += "Z";
  const t = new Date(s).getTime();
  if (isNaN(t)) return "";
  const secs = Math.floor((Date.now() - t) / 1000);
  if (secs < 60) return "just now";
  const m = Math.floor(secs / 60); if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function RecentActivity({ activity, onRefresh, refreshing }) {
  let body;
  if (!activity) {
    body = <Skeleton height={120} />;
  } else if (activity.error) {
    body = <div style={{ color: C.text3, fontSize: 13 }}>Couldn’t load recent activity.</div>;
  } else if (activity.available === false) {
    body = <PostHogUnavailable info={activity} subtitle="The live feed comes from PostHog." />;
  } else if (!activity.rows || activity.rows.length === 0) {
    body = <div style={{ color: C.text3, fontSize: 13 }}>No recent activity yet.</div>;
  } else {
    body = (
      <div>
        {activity.rows.map((r, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "6px 0",
            borderBottom: `1px solid ${C.border}`, font: `500 13px ${FONT_DISPLAY}`,
          }}>
            <span style={{
              fontWeight: 700, color: C.text1, flex: "0 0 auto", maxWidth: 120,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>{r.parent_first}</span>
            <span style={{ color: C.text2, flex: 1, minWidth: 0 }}>{EVENT_LABELS[r.event] || r.event}</span>
            <span style={{ color: C.text3, flex: "0 0 auto", fontSize: 12 }}>{relTime(r.timestamp)}</span>
          </div>
        ))}
      </div>
    );
  }
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span style={{ font: `700 15px ${FONT_DISPLAY}`, color: C.text1, display: "flex", gap: 8, alignItems: "center" }}>
          Recent activity <Src>PostHog</Src>
        </span>
        <Button variant="ghost" onClick={onRefresh} disabled={refreshing}>{refreshing ? "…" : "Refresh"}</Button>
      </div>
      {body}
    </Card>
  );
}

function CalendarPlatform({ data }) {
  if (!data) return null;
  const rows = [
    { label: "BYGA", n: data.byga || 0 },
    { label: "PlayMetrics", n: data.playmetrics || 0 },
    { label: "Not connected", n: data.not_connected || 0 },
  ];
  return (
    <Card>
      <SectionTitle>Calendar platform <Src>DB</Src></SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {rows.map((r) => (
          <div key={r.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", font: `600 14px ${FONT_DISPLAY}`, color: C.text2 }}>
            <span>{r.label}</span>
            <span style={{ font: `800 15px ${FONT_DISPLAY}`, color: C.text1 }}>
              {r.n} {r.n === 1 ? "family" : "families"}
            </span>
          </div>
        ))}
      </div>
      <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginTop: 10 }}>
        Current connections, counted per family.
      </div>
    </Card>
  );
}

function SectionTitle({ children }) {
  return <div style={{ font: `700 15px ${FONT_DISPLAY}`, color: C.text1, marginBottom: 12, display: "flex", gap: 8, alignItems: "center" }}>{children}</div>;
}
function Src({ children }) {
  return <span style={{ font: `700 10px ${FONT_DISPLAY}`, color: C.text3, background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 6, padding: "1px 7px", letterSpacing: "0.03em" }}>{children}</span>;
}
function HealthRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", font: `500 14px ${FONT_DISPLAY}`, color: C.text2 }}>
      <span>{label}</span><span style={{ font: `800 15px ${FONT_DISPLAY}`, color: C.text1 }}>{value}</span>
    </div>
  );
}

// App-health card. The "Problem reports (7d)" row is expandable so the team can
// read the actual reported problems (fetched lazily on first open), not just the
// count. Reports come from our own DB (the /support/report submissions).
function AppHealth({ appHealth, onLoggedOut }) {
  const bugs = appHealth.problem_reports_7d;
  const [open, setOpen] = useState(false);
  const [reports, setReports] = useState(null);   // null = not loaded, [] = loaded-empty
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next && reports === null && !loading) {
      setLoading(true); setErr("");
      try {
        const data = await adminFetch(`/analytics/problem-reports?days=7`);
        setReports(data.reports || []);
      } catch (e) {
        if (e instanceof AuthError) return onLoggedOut();
        setErr(e.message);
      } finally { setLoading(false); }
    }
  }

  const expandable = bugs > 0;
  return (
    <Card>
      <SectionTitle>App health <Src>DB</Src></SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
        <div
          onClick={expandable ? toggle : undefined}
          role={expandable ? "button" : undefined}
          tabIndex={expandable ? 0 : undefined}
          onKeyDown={expandable ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } } : undefined}
          style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            font: `500 14px ${FONT_DISPLAY}`, color: C.text2,
            cursor: expandable ? "pointer" : "default",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            Problem reports (7d)
            {expandable && (
              <span style={{ font: `700 11px ${FONT_DISPLAY}`, color: C.brand }}>
                {open ? "Hide" : "View"}
              </span>
            )}
          </span>
          <span style={{ font: `800 15px ${FONT_DISPLAY}`, color: C.text1 }}>{bugs}</span>
        </div>
        {open && (
          <div style={{ marginTop: 2, marginBottom: 4 }}>
            {loading && <Skeleton height={70} />}
            {err && <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text3 }}>Couldn’t load reports: {err}</div>}
            {reports && reports.length === 0 && !loading && (
              <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text3 }}>No problem reports in the last 7 days.</div>
            )}
            {reports && reports.map((r) => <ProblemReport key={r.id} report={r} />)}
          </div>
        )}
        <HealthRow label="Feature ideas (7d)" value={appHealth.feature_ideas_7d} />
      </div>
      <div style={{ font: `600 13px ${FONT_DISPLAY}`, color: C.text2, marginBottom: 8 }}>Events: synced vs manual</div>
      <PieChart data={appHealth.event_sources} />
    </Card>
  );
}

function ProblemReport({ report }) {
  const meta = [
    report.role_hint,
    report.platform,
    report.app_version ? `v${report.app_version}` : null,
    relTime(report.created_at),
  ].filter(Boolean).join(" · ");
  return (
    <div style={{ padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
      <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text1, whiteSpace: "pre-wrap", lineHeight: 1.4 }}>
        {report.description}
      </div>
      {meta && <div style={{ font: `500 11px ${FONT_DISPLAY}`, color: C.text3, marginTop: 3 }}>{meta}</div>}
    </div>
  );
}

function PostHogUnavailable({ info, subtitle }) {
  return (
    <div style={{
      font: `600 13px ${FONT_DISPLAY}`, color: C.text2, background: C.surface2,
      border: `1px dashed ${C.border2}`, borderRadius: 10, padding: "16px", textAlign: "center",
    }}>
      {info?.reason || "PostHog not connected"}
      <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginTop: 4 }}>{subtitle}</div>
    </div>
  );
}

function TopEvents({ events }) {
  if (!events || !events.available) {
    return <PostHogUnavailable info={events}
      subtitle="Top events by volume come from PostHog." />;
  }
  // PostHog client returns shaped rows: { data: { rows: [{event, count}] } }.
  const rows = events.data?.rows || [];
  if (rows.length === 0) return <div style={{ color: C.text3, fontSize: 13 }}>No events yet — they’ll appear as the app fires them.</div>;
  return (
    <div>
      {rows.slice(0, 10).map((r) => (
        <div key={r.event} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: `1px solid ${C.border}`, font: `500 13px ${FONT_DISPLAY}`, color: C.text1 }}>
          <span>{r.event}</span><span style={{ color: C.text2 }}>{r.count}</span>
        </div>
      ))}
    </div>
  );
}

function Retention({ retention }) {
  const points = (retention.points || []).map((p) => ({ date: p.week_start, count: p.active }));
  return (
    <>
      {retention.note && <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginBottom: 8 }}>{retention.note}</div>}
      <LineChart points={points} height={150} />
    </>
  );
}
