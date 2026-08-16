import { useEffect, useState } from "react";
import { adminFetch, AuthError } from "./adminApi";
import { C, FONT_DISPLAY } from "./theme";
import { Card, Button, Spinner, ErrorRetry } from "./ui";

// Operations dashboard: a "needs attention" feed (real signals) + metric cards +
// a weekly-activity heatmap. `onNavigate(section, id?)` jumps to the relevant page.
export default function AdminActionHub({ onLoggedOut, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load(force) {
    force ? setRefreshing(true) : setLoading(true);
    setError(false);
    try {
      setData(await adminFetch("/action-hub"));
    } catch (err) {
      if (err instanceof AuthError) return onLoggedOut();
      setError(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  if (loading) return <div style={{ display: "flex", justifyContent: "center", padding: 80 }}><Spinner size={28} /></div>;
  if (error || !data) return <ErrorRetry message="Couldn’t load the Action Hub." onRetry={() => load(false)} />;

  const time = new Date(data.as_of).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  const h = data.health;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <h1 style={{ font: `800 26px ${FONT_DISPLAY}`, color: C.text1, margin: 0 }}>AthFuelPath Mission Control</h1>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <span style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text3 }}>as of {time}</span>
          <Button variant="ghost" onClick={() => load(true)} disabled={refreshing}>{refreshing ? "Refreshing…" : "Refresh"}</Button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
        {/* Left — attention feed */}
        <div style={{ flex: "2 1 340px", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
            <h2 style={{ font: `800 18px ${FONT_DISPLAY}`, color: C.text1, margin: 0 }}>Attention required</h2>
            <span style={{
              font: `800 12px ${FONT_DISPLAY}`,
              color: data.urgent_count > 0 ? "#991b1b" : "#1E5A45",
              background: data.urgent_count > 0 ? "#fee2e2" : C.brandPale,
              borderRadius: 999, padding: "2px 10px",
            }}>
              {data.urgent_count} urgent
            </span>
          </div>
          {data.attention.length === 0 ? (
            <Card><span style={{ color: C.text3, fontSize: 14 }}>🎉 Nothing needs attention right now.</span></Card>
          ) : (
            data.attention.map((it, i) => <AlertCard key={i} item={it} onNavigate={onNavigate} />)
          )}
        </div>

        {/* Right — metrics + heatmap */}
        <div style={{ flex: "3 1 420px", minWidth: 0, display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{
            display: "flex", gap: 12, alignItems: "flex-start",
            background: h.status === "red" ? C.dangerBg : C.brandGhost,
            border: `1px solid ${h.status === "red" ? C.dangerBorder : C.brandLight}`,
            borderRadius: 14, padding: "14px 16px",
          }}>
            <span style={{ fontSize: 20 }}>{h.icon}</span>
            <div>
              <div style={{ font: `800 16px ${FONT_DISPLAY}`, color: C.text1 }}>{h.headline}</div>
              <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text2, marginTop: 2 }}>{h.detail}</div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
            {data.metrics.map((m) => (
              <Card key={m.label} style={{ padding: 16 }}>
                <div style={{ font: `700 11px ${FONT_DISPLAY}`, color: C.text3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{m.label}</div>
                <div style={{ font: `800 30px ${FONT_DISPLAY}`, color: C.text1, marginTop: 6, lineHeight: 1.1 }}>{m.value}</div>
                <div style={{ font: `500 12px ${FONT_DISPLAY}`, color: C.text3, marginTop: 4 }}>{m.sub}</div>
              </Card>
            ))}
          </div>

          <Card>
            <div style={{ font: `700 15px ${FONT_DISPLAY}`, color: C.text1, marginBottom: 4 }}>Activity — last {data.heatmap.weeks} weeks</div>
            <div style={{ font: `400 12px ${FONT_DISPLAY}`, color: C.text3, marginBottom: 14 }}>Active athletes per day (darker = more active).</div>
            <Heatmap points={data.heatmap.points} weeks={data.heatmap.weeks} max={data.heatmap.max} />
          </Card>
        </div>
      </div>
    </div>
  );
}

function AlertCard({ item, onNavigate }) {
  const accent = item.severity === "error" ? C.danger : C.warm;
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderLeft: `4px solid ${accent}`,
      borderRadius: 12, padding: "12px 14px", marginBottom: 10,
    }}>
      <div style={{ display: "flex", gap: 7, alignItems: "center", font: `800 11px ${FONT_DISPLAY}`, color: accent, letterSpacing: "0.04em", textTransform: "uppercase" }}>
        <span>{item.icon}</span> {item.category}
      </div>
      <div style={{ font: `700 15px ${FONT_DISPLAY}`, color: C.text1, marginTop: 5 }}>{item.title}</div>
      <div style={{ font: `400 13px ${FONT_DISPLAY}`, color: C.text2, marginTop: 2 }}>{item.detail}</div>
      {item.action && (
        <div style={{ marginTop: 10 }}>
          <Button variant="ghost" onClick={() => onNavigate(item.action.section, item.action.id)}>{item.action.label} →</Button>
        </div>
      )}
    </div>
  );
}

// GitHub-style activity heatmap: columns = weeks, rows = weekday.
function Heatmap({ points, weeks = 8, max = 1 }) {
  const counts = {};
  for (const p of points) counts[p.date] = p.count;
  const hi = Math.max(1, max);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setDate(start.getDate() - (weeks * 7 - 1));
  start.setDate(start.getDate() - start.getDay()); // back to Sunday

  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const cols = [];
  const cursor = new Date(start);
  while (cursor <= today) {
    const col = [];
    for (let d = 0; d < 7; d++) {
      const future = cursor > today;
      col.push({ iso: iso(cursor), count: counts[iso(cursor)] || 0, future });
      cursor.setDate(cursor.getDate() + 1);
    }
    cols.push(col);
  }
  const color = (c) => {
    if (c.future) return "transparent";
    if (c.count === 0) return C.surface2;
    const t = c.count / hi;
    return t > 0.66 ? "#059669" : t > 0.33 ? "#34d399" : "#a7f3d0";
  };
  return (
    <div>
      <div style={{ display: "flex", gap: 3 }}>
        {cols.map((col, ci) => (
          <div key={ci} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {col.map((c, ri) => (
              <span key={ri} title={c.future ? "" : `${c.iso}: ${c.count} active`} style={{
                width: 14, height: 14, borderRadius: 3, background: color(c),
                border: c.future ? "none" : `1px solid ${C.border}`,
              }} />
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 10, font: `500 11px ${FONT_DISPLAY}`, color: C.text3 }}>
        Less
        {[C.surface2, "#a7f3d0", "#34d399", "#059669"].map((bg) => (
          <span key={bg} style={{ width: 12, height: 12, borderRadius: 3, background: bg, border: `1px solid ${C.border}` }} />
        ))}
        More
      </div>
    </div>
  );
}
