import LogDuo from "./LogDuo";

export default function MissionItem({ item, isDone, cameraAvailable, onPhoto, onVoice, onText }) {
  const state = isDone ? "done" : item.state;
  const tag   = isDone ? "DONE" : item.tag;

  const boxStyle = {
    done:    { border: "1px solid rgba(45,106,79,.3)", background: "rgba(45,106,79,.12)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "17px", color: "#2d6a4f" },
    urgent:  { border: "1.5px solid rgba(180,83,9,.5)",  background: "rgba(180,83,9,.08)" },
    build:   { border: "1.5px solid rgba(180,83,9,.35)", background: "rgba(217,119,6,.08)" },
    pending: { border: "1.5px solid #dce8e0", background: "transparent" },
  };

  const tagStyle = {
    DONE:     { background: "rgba(45,106,79,.10)", color: "#2d6a4f" },
    NOW:      { background: "rgba(180,83,9,.12)",  color: "#b45309", animation: "athfuelpath-pulse 1.4s infinite" },
    BOOST:    { background: "rgba(37,99,235,.10)", color: "#1d4ed8" },
    UPCOMING: { background: "#f4f8f5",             color: "#4a6358" },
  };

  return (
    <div style={{ ...s.row, opacity: isDone ? 0.55 : 1 }}>
      <div style={{ ...s.checkBox, ...(boxStyle[state] || boxStyle.pending) }}>
        {state === "done" ? "✓" : null}
      </div>

      <div style={s.body}>
        {/* Top row: label/sub on left, time+tag on right */}
        <div style={s.topRow}>
          <div style={s.labelCol}>
            <div style={{ ...s.label, ...(isDone ? s.labelDone : {}) }}>{item.label}</div>
            {(item.carbs_g != null || item.protein_g != null)
              ? <div style={s.sub}>
                  {item.carbs_g  != null && <span style={s.macroChip("#16a34a", "#e6f4ec")}>{item.carbs_g}g carbs</span>}
                  {item.protein_g != null && <span style={s.macroChip("#d97706", "#fef3c7")}>{item.protein_g}g protein</span>}
                </div>
              : item.sub && <div style={s.sub}>{item.sub}</div>
            }
          </div>
          <div style={s.timeTagCol}>
            <span style={s.time}>{item.time}</span>
            {isDone && (
              <span style={{ ...s.tag, ...(tagStyle[tag] || tagStyle.DONE) }}>{tag}</span>
            )}
          </div>
        </div>

        {/* On-card duo — only when not yet logged */}
        {!isDone && (
          <LogDuo
            window={{ id: item.meal_type, name: item.label }}
            cameraAvailable={cameraAvailable}
            onPhoto={onPhoto}
            onVoice={onVoice}
            onText={onText}
          />
        )}
      </div>
    </div>
  );
}

const s = {
  row:        { display: "flex", alignItems: "flex-start", gap: "10px", padding: "13px 14px", borderBottom: "1px solid #dce8e0" },
  checkBox:   { width: "22px", height: "22px", borderRadius: "5px", flexShrink: 0, marginTop: "3px" },
  body:       { flex: 1, minWidth: 0 },
  topRow:     { display: "flex", alignItems: "flex-start", gap: "8px" },
  labelCol:   { flex: 1, minWidth: 0 },
  label:      { fontSize: "16px", fontWeight: "600", color: "#1b3a2a", lineHeight: "1.3", marginBottom: "3px" },
  labelDone:  { textDecoration: "line-through", color: "#4a6358" },
  sub:        { fontSize: "14px", color: "#4a6358", fontWeight: "400", lineHeight: "1.4", display: "flex", flexWrap: "wrap", gap: "4px" },
  macroChip:  (color, bg) => ({ fontSize: "12px", fontWeight: "700", color, background: bg, borderRadius: "99px", padding: "2px 7px", display: "inline-block" }),
  timeTagCol: { display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "4px", flexShrink: 0 },
  time:       { fontSize: "14px", color: "#4a6358", fontWeight: "400", whiteSpace: "nowrap" },
  tag:        { fontSize: "12px", fontWeight: "600", letterSpacing: ".04em", padding: "3px 8px", borderRadius: "3px", whiteSpace: "nowrap" },
};
