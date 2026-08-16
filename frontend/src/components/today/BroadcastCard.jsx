import { useState, useEffect } from "react";

// ── Countdown helpers ──────────────────────────────────────────────────────
function computeCountdown(events) {
  const now = new Date();
  const upcoming = events
    .map(e => {
      if (!e.start_time) return null;
      const [h, m] = e.start_time.split(":").map(Number);
      const t = new Date(now);
      t.setHours(h, m, 0, 0);
      return { ...e, eventTime: t, diff: t - now };
    })
    .filter(e => e && e.diff > 0)
    .sort((a, b) => a.diff - b.diff);

  if (!upcoming.length) return { text: "IN PROGRESS", mins: 0, isLive: true };
  const mins = Math.floor(upcoming[0].diff / 60000);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return { text: `${h}:${String(m).padStart(2, "0")}`, mins, isLive: false };
}

// ── Score helpers ──────────────────────────────────────────────────────────
function scoreColor(score) {
  if (score >= 75) return "#2d6a4f";
  return "#b45309";
}

function taglineContent(score) {
  if (score >= 85) return { emoji: "🏆", text: "Fueled for a career-best performance today." };
  if (score >= 70) return { emoji: "⚡", text: "One snack away from game-ready — grab something now!" };
  if (score >= 50) return { emoji: "📈", text: "Building toward peak — an iron-rich meal will get you there." };
  return { emoji: "🌱", text: "Let's power up — your next meal changes everything." };
}

// ── ReadinessDial ─────────────────────────────────────────────────────────
function ReadinessDial({ score }) {
  const [displayed, setDisplayed] = useState(0);
  const circumference = 182; // 2π × 29

  useEffect(() => {
    let interval;
    const timer = setTimeout(() => {
      let val = 0;
      interval = setInterval(() => {
        val = Math.min(val + 2, score);
        setDisplayed(val);
        if (val >= score) clearInterval(interval);
      }, 14);
    }, 200);
    return () => { clearTimeout(timer); clearInterval(interval); };
  }, [score]);

  const offset = circumference - (circumference * displayed) / 100;
  const color = scoreColor(score);
  const statusLabel = score >= 75 ? "READY" : score >= 50 ? "BUILDING" : "LOW";

  return (
    <div style={rd.wrap}>
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="29" fill="none" stroke="#dce8e0" strokeWidth="5" />
        <circle
          cx="36" cy="36" r="29" fill="none"
          stroke={color} strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 36 36)"
          style={{ transition: "stroke-dashoffset 0.9s cubic-bezier(.4,0,.2,1)" }}
        />
        <text x="36" y="33" textAnchor="middle" fill={color} fontSize="16" fontWeight="800" fontFamily="Nunito,sans-serif">{displayed}</text>
        <text x="36" y="44" textAnchor="middle" fill="#4a6358" fontSize="8" fontFamily="DM Sans,sans-serif" letterSpacing="1">{statusLabel}</text>
      </svg>
      <div style={rd.status}>{statusLabel}</div>
    </div>
  );
}
const rd = {
  wrap:   { display: "flex", flexDirection: "column", alignItems: "center", gap: "2px", flexShrink: 0 },
  status: { fontSize: "12px", textTransform: "uppercase", letterSpacing: ".05em", color: "#4a6358" },
};

// ── BroadcastCard ─────────────────────────────────────────────────────────
export default function BroadcastCard({ athlete, events = [], trafficLight, fuelScore, onNavigateMealPlan }) {
  const [countdown, setCountdown] = useState(() => computeCountdown(events));

  useEffect(() => {
    const interval = setInterval(() => setCountdown(computeCountdown(events)), 30000);
    return () => clearInterval(interval);
  }, [events]);

  const score = fuelScore ?? 0;
  const tl = trafficLight ?? {};
  const isUrgent = !countdown.isLive && countdown.mins < 30;
  const tagline = taglineContent(score);

  const hasEvent = events.length > 0;
  const eventStr = hasEvent
    ? `${events[0].event_type?.replace(/_/g, " ")} · ${events[0].event_name || "Training"}`
    : "Rest Day";

  const carbsPct  = tl.carbs_g?.pct_met  ?? 0;
  const ironPct   = tl.iron_mg?.pct_met  ?? 0;
  const ironSub   = ironPct < 50 ? "build today" : ironPct < 80 ? "building" : "on track";

  return (
    <div style={bc.card}>
      {/* Ticker */}
      <div style={bc.ticker}>
        <div style={bc.liveDot} />
        <span style={bc.liveLabel}>LIVE</span>
        <div style={bc.tickerSep} />
        <span style={bc.tickerEvent}>{eventStr.toUpperCase()}</span>
        <span style={{ ...bc.tickerCountdown, color: "#b45309" }}>
          {hasEvent ? (countdown.isLive ? "IN PROGRESS" : `${countdown.text} TO KICKOFF`) : "NO EVENT"}
        </span>
      </div>

      {/* Identity */}
      <div style={bc.identityRow}>
        <div>
          {(athlete.position || athlete.competition_level) && (
            <div style={bc.positionLine}>
              {[athlete.position, athlete.competition_level].filter(Boolean).join(" · ")}
            </div>
          )}
          <div style={bc.nameBlock}>
            <div style={bc.firstName}>{athlete.first_name}</div>
            {athlete.last_name && <div style={bc.lastName}>{athlete.last_name}</div>}
          </div>
          {athlete.team_name && (
            <div style={bc.teamLine}>{athlete.team_name}</div>
          )}
        </div>
        <ReadinessDial score={score} />
      </div>

      {/* Tagline bar */}
      <div style={bc.taglineBar} onClick={onNavigateMealPlan} role="button">
        <span style={bc.taglineEmoji}>{tagline.emoji}</span>
        <span style={bc.taglineText}>{tagline.text}</span>
        <span style={bc.taglineArrow}>→</span>
      </div>

      {/* Stats row */}
      <div style={bc.statsRow}>
        <div style={bc.statCell}>
          <div style={bc.statLabel}>Fuel score</div>
          <div style={{ ...bc.statValue, color: scoreColor(score) }}>{score}</div>
          <div style={bc.statSub}>/ 100</div>
        </div>
        <div style={bc.statCell}>
          <div style={bc.statLabel}>Carbs</div>
          <div style={{ ...bc.statValue, color: carbsPct >= 80 ? "#2d6a4f" : "#b45309" }}>
            {carbsPct}%
          </div>
          <div style={bc.statSub}>of target</div>
        </div>
        <div style={{ ...bc.statCell }}>
          <div style={bc.statLabel}>Iron</div>
          <div style={{ ...bc.statValue, color: ironPct >= 80 ? "#2d6a4f" : "#b45309" }}>
            {ironPct}%
          </div>
          <div style={bc.statSub}>{ironSub}</div>
        </div>
        <div style={{ ...bc.statCell, borderRight: "none" }}>
          <div style={bc.statLabel}>Kickoff</div>
          <div style={{ ...bc.statValue, color: "#b45309" }}>
            {hasEvent ? (countdown.isLive ? "—" : countdown.text) : "—"}
          </div>
          <div style={bc.statSub}>{hasEvent && countdown.isLive ? "LIVE" : "hrs·min"}</div>
        </div>
      </div>
    </div>
  );
}

const bc = {
  card:          { background: "#fff", borderBottom: "1px solid #dce8e0" },
  ticker:        { background: "#f4f8f5", borderBottom: "1px solid #dce8e0", height: "44px", padding: "0 14px", display: "flex", alignItems: "center", gap: "8px" },
  liveDot:       { width: "7px", height: "7px", borderRadius: "50%", background: "#e05a4a", animation: "athfuelpath-pulse 1.4s infinite", flexShrink: 0 },
  liveLabel:     { fontSize: "12px", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: "700", color: "#e05a4a" },
  tickerSep:     { width: "1px", height: "14px", background: "#dce8e0" },
  tickerEvent:   { fontSize: "13px", textTransform: "uppercase", letterSpacing: ".04em", color: "#4a6358", fontWeight: "400", flex: 1, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" },
  tickerCountdown: { fontSize: "13px", fontWeight: "700", textTransform: "uppercase", flexShrink: 0 },
  identityRow:   { padding: "16px 14px 12px", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "12px" },
  positionLine:  { fontSize: "12px", textTransform: "uppercase", letterSpacing: ".08em", color: "#4a6358", fontWeight: "500", marginBottom: "4px" },
  nameBlock:     { lineHeight: "1.0" },
  firstName:     { fontFamily: "'Nunito', sans-serif", fontSize: "29px", fontWeight: "800", letterSpacing: "-.04em", color: "#1b3a2a" },
  lastName:      { fontFamily: "'Nunito', sans-serif", fontSize: "29px", fontWeight: "800", letterSpacing: "-.04em", color: "#1b3a2a" },
  teamLine:      { fontSize: "13px", color: "#4a6358", fontWeight: "400", marginTop: "4px" },
  taglineBar:    { margin: "0 14px 14px", borderRadius: "9px", padding: "13px 14px", background: "#2d6a4f", display: "flex", alignItems: "center", gap: "10px", cursor: "pointer" },
  taglineEmoji:  { fontSize: "21px" },
  taglineText:   { fontFamily: "'Nunito', sans-serif", fontSize: "16px", fontWeight: "800", color: "#d4ead8", letterSpacing: "-.01em", lineHeight: "1.3", flex: 1 },
  taglineArrow:  { fontSize: "17px", color: "#b7e4c7", opacity: ".5" },
  statsRow:      { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", borderTop: "1px solid #dce8e0" },
  statCell:      { padding: "12px 10px", borderRight: "1px solid #dce8e0" },
  statLabel:     { fontSize: "11px", textTransform: "uppercase", letterSpacing: ".07em", color: "#4a6358", marginBottom: "3px" },
  statValue:     { fontFamily: "'Nunito', sans-serif", fontSize: "19px", fontWeight: "800", letterSpacing: "-.02em", lineHeight: "1", marginBottom: "2px" },
  statSub:       { fontSize: "12px", color: "#4a6358", fontWeight: "400" },
};
