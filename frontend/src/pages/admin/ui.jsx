// Reusable admin primitives + hand-rolled SVG charts. No charting dependency —
// matches the app's existing hand-rolled data-viz convention (WeeklyHeatmap).
import { C, FONT_DISPLAY, CHIP_META } from "./theme";

// Initials avatar (no parent photos exist) — deterministic color from the name.
const _AV = ["#1E5A45", "#0e7490", "#7c3aed", "#b45309", "#be123c", "#1d4ed8", "#047857", "#9333ea"];
export function Avatar({ name, size = 40 }) {
  const clean = (name || "").replace(/\[deleted\]/i, "").trim();
  const initials = (clean.split(/\s+/).slice(0, 2).map((w) => w[0] || "").join("") || "?").toUpperCase();
  let h = 0;
  for (const ch of clean) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return (
    <span style={{
      width: size, height: size, borderRadius: "50%", background: _AV[h % _AV.length], color: "#fff",
      display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      font: `700 ${Math.round(size * 0.4)}px ${FONT_DISPLAY}`, letterSpacing: "0.02em",
    }}>{initials}</span>
  );
}

export function Card({ children, style }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 16,
      boxShadow: C.shadowSm, padding: 20, ...style,
    }}>{children}</div>
  );
}

export function Button({ children, onClick, variant = "primary", disabled, type = "button", style }) {
  const base = {
    font: `600 14px ${FONT_DISPLAY}`, borderRadius: 8, padding: "9px 16px",
    cursor: disabled ? "not-allowed" : "pointer", border: "1px solid transparent",
    opacity: disabled ? 0.55 : 1, transition: "filter .15s",
  };
  const variants = {
    primary: { background: C.brand, color: "#fff" },
    ghost: { background: "transparent", color: C.text2, border: `1px solid ${C.border2}` },
    danger: { background: C.danger, color: "#fff" },
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      style={{ ...base, ...variants[variant], ...style }}>{children}</button>
  );
}

export function TextInput({ value, onChange, placeholder, type = "text", style, onKeyDown }) {
  return (
    <input value={value} onChange={onChange} placeholder={placeholder} type={type} onKeyDown={onKeyDown}
      style={{
        font: `400 14px ${FONT_DISPLAY}`, padding: "9px 12px", borderRadius: 8,
        border: `1px solid ${C.border2}`, background: C.surface, color: C.text1,
        outline: "none", width: "100%", boxSizing: "border-box", ...style,
      }} />
  );
}

export function Select({ value, onChange, options, style }) {
  return (
    <select value={value} onChange={onChange} style={{
      font: `500 13px ${FONT_DISPLAY}`, padding: "8px 10px", borderRadius: 8,
      border: `1px solid ${C.border2}`, background: C.surface, color: C.text2, cursor: "pointer", ...style,
    }}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function Chip({ kind }) {
  const m = CHIP_META[kind] || { label: kind, fg: C.text3, bg: C.surface2, border: C.border };
  return (
    <span style={{
      font: `700 11px ${FONT_DISPLAY}`, color: m.fg, background: m.bg,
      border: `1px solid ${m.border}`, borderRadius: 999, padding: "2px 9px",
      letterSpacing: "0.02em", whiteSpace: "nowrap",
    }}>{m.label}</span>
  );
}

// Smarter calendar state. Distinguishes recurring auto-sync (BYGA / PlayMetrics),
// a one-time uploaded .ics file, hand-entered events, and a truly empty schedule.
// `count` is the imported-event count for "imported", total-event count for "manual".
export function CalendarBadge({ kind, count }) {
  const n = count || 0;
  const map = {
    byga: { label: "BYGA ✓", fg: C.brand, bg: C.brandGhost, border: C.brandLight },
    playmetrics: { label: "PlayMetrics ✓", fg: "#4a8fc4", bg: "#eef5fb", border: "#b8d8ef" },
    imported: { label: n ? `Calendar file · ${n}` : "Calendar file ✓", fg: C.brand, bg: C.brandGhost, border: C.brandLight },
    manual: { label: n ? `Manual · ${n}` : "Manual", fg: C.text2, bg: C.surface2, border: C.border2 },
    none: { label: "No schedule ⚠", fg: "#9a6a1e", bg: C.warmLight, border: "#f0d9a8" },
  };
  const m = map[kind] || map.none;
  return (
    <span style={{
      font: `700 11px ${FONT_DISPLAY}`, color: m.fg, background: m.bg,
      border: `1px solid ${m.border}`, borderRadius: 6, padding: "2px 8px",
    }}>{m.label}</span>
  );
}

export function Spinner({ size = 22 }) {
  return (
    <div style={{
      width: size, height: size, border: `3px solid ${C.brandPale}`,
      borderTopColor: C.brand, borderRadius: "50%", animation: "athfuelpath-spin 0.8s linear infinite",
    }} />
  );
}

export function EmptyState({ title, subtitle }) {
  return (
    <div style={{ textAlign: "center", padding: "48px 20px", color: C.text3 }}>
      <div style={{ font: `700 16px ${FONT_DISPLAY}`, color: C.text2 }}>{title}</div>
      {subtitle && <div style={{ font: `400 14px ${FONT_DISPLAY}`, marginTop: 6 }}>{subtitle}</div>}
    </div>
  );
}

export function Skeleton({ height = 16, width = "100%", style }) {
  return (
    <div style={{
      height, width, borderRadius: 8, background: C.surface2,
      animation: "athfuelpath-pulse 1.4s ease-in-out infinite", ...style,
    }} />
  );
}

export function ErrorRetry({ message, onRetry }) {
  return (
    <div style={{ textAlign: "center", padding: 32, color: C.danger }}>
      <div style={{ font: `600 15px ${FONT_DISPLAY}` }}>{message || "Something went wrong."}</div>
      {onRetry && <div style={{ marginTop: 12 }}><Button variant="ghost" onClick={onRetry}>Retry</Button></div>}
    </div>
  );
}

// ── Charts (hand-rolled SVG) ─────────────────────────────────────────────────
export function StatCard({ label, value, sub }) {
  return (
    <Card style={{ padding: 18 }}>
      <div style={{ font: `600 12px ${FONT_DISPLAY}`, color: C.text3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
      <div style={{ font: `800 30px ${FONT_DISPLAY}`, color: C.text1, marginTop: 6, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ font: `500 13px ${FONT_DISPLAY}`, color: C.text3, marginTop: 4 }}>{sub}</div>}
    </Card>
  );
}

export function LineChart({ points, height = 180 }) {
  const w = 640, h = height, pad = 28;
  if (!points || points.length === 0) return <EmptyState title="No data in range" />;
  const max = Math.max(1, ...points.map((p) => p.count));
  const stepX = points.length > 1 ? (w - pad * 2) / (points.length - 1) : 0;
  const coords = points.map((p, i) => {
    const x = pad + i * stepX;
    const y = h - pad - (p.count / max) * (h - pad * 2);
    return [x, y];
  });
  const path = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${path} L${coords[coords.length - 1][0].toFixed(1)},${h - pad} L${coords[0][0].toFixed(1)},${h - pad} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="Signups over time">
      <path d={area} fill={C.brandPale} opacity="0.5" />
      <path d={path} fill="none" stroke={C.brand} strokeWidth="2.5" strokeLinejoin="round" />
      {coords.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.5" fill={C.brand} />)}
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke={C.border} strokeWidth="1" />
    </svg>
  );
}

export function FunnelBars({ steps }) {
  if (!steps || steps.length === 0) return <EmptyState title="No funnel data" />;
  const max = Math.max(1, ...steps.map((s) => s.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {steps.map((s, i) => (
        <div key={s.label}>
          <div style={{ display: "flex", justifyContent: "space-between", font: `600 13px ${FONT_DISPLAY}`, color: C.text2, marginBottom: 4 }}>
            <span>{s.label}</span>
            <span style={{ color: C.text3 }}>
              {s.value} · {s.pct_of_start}% of start{i > 0 ? ` · ${s.pct_of_prev}% step` : ""}
            </span>
          </div>
          <div style={{ background: C.surface2, borderRadius: 8, height: 26, overflow: "hidden" }}>
            <div style={{
              width: `${(s.value / max) * 100}%`, height: "100%",
              background: `linear-gradient(90deg, ${C.brand}, ${C.brandMid})`, borderRadius: 8,
              minWidth: s.value > 0 ? 4 : 0, transition: "width .4s",
            }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function PieChart({ data, size = 150 }) {
  const entries = Object.entries(data || {}).filter(([, v]) => v > 0);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  if (total === 0) return <EmptyState title="No events yet" />;
  const palette = [C.brand, C.warm, C.brandMid, "#4a8fc4", C.brandLight, C.text3];
  const r = size / 2, cx = r, cy = r;
  let acc = 0;
  const arcs = entries.map(([k, v], i) => {
    const start = (acc / total) * 2 * Math.PI;
    acc += v;
    const end = (acc / total) * 2 * Math.PI;
    const large = end - start > Math.PI ? 1 : 0;
    const x1 = cx + r * Math.sin(start), y1 = cy - r * Math.cos(start);
    const x2 = cx + r * Math.sin(end), y2 = cy - r * Math.cos(end);
    return { d: `M${cx},${cy} L${x1.toFixed(1)},${y1.toFixed(1)} A${r},${r} 0 ${large} 1 ${x2.toFixed(1)},${y2.toFixed(1)} Z`, color: palette[i % palette.length], k, v };
  });
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Event sources">
        {arcs.map((a) => <path key={a.k} d={a.d} fill={a.color} stroke="#fff" strokeWidth="1" />)}
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {arcs.map((a) => (
          <div key={a.k} style={{ display: "flex", alignItems: "center", gap: 8, font: `500 13px ${FONT_DISPLAY}`, color: C.text2 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: a.color }} />
            {a.k} — {a.v} ({Math.round((a.v / total) * 100)}%)
          </div>
        ))}
      </div>
    </div>
  );
}
