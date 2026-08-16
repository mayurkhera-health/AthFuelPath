import { useState, useEffect } from "react";

const API = import.meta.env.VITE_API_URL ?? "";

export default function ParentReport({ athleteId, weekStart }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    setReport(null);
    fetch(`${API}/api/reports/${athleteId}/weekly?week_start=${weekStart}`)
      .then((r) => {
        if (!r.ok) throw new Error("Could not load report");
        return r.json();
      })
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [athleteId, weekStart]);

  if (loading) {
    return (
      <div style={s.card}>
        <div style={s.header}>
          <div style={s.title}>Weekly Fuel Report</div>
        </div>
        <div style={s.loadingBody}>
          <div style={s.spinner} />
          <p style={s.loadingText}>Generating your weekly report with AI…</p>
          <p style={s.loadingSub}>
            Analysing 7 days of nutrition data — usually takes 10–20 seconds.
          </p>
        </div>
      </div>
    );
  }

  if (error || !report) return null;

  const grade = report.letter_grade ?? "—";
  const whatWentWell = Array.isArray(report.what_went_well) ? report.what_went_well : [];
  const focusAreas = Array.isArray(report.nutrients_to_focus_on)
    ? report.nutrients_to_focus_on.slice(0, 1)
    : [];
  const actions = Array.isArray(report.nutrients_to_focus_on)
    ? report.nutrients_to_focus_on.slice(0, 2)
    : [];
  const featuredRecipe = report.featured_recipe ?? null;
  const gameReadiness = report.game_day_readiness ?? null;

  return (
    <div style={s.card}>
      <div style={s.header}>
        <div>
          <div style={s.title}>Weekly Fuel Report</div>
          <div style={s.headerSub}>AI-generated · science-backed</div>
        </div>
        <div style={s.gradeBlock}>
          <div style={s.grade}>{grade}</div>
          <div style={s.gradeSub}>week avg</div>
        </div>
      </div>

      {whatWentWell.length > 0 && (
        <div style={s.section}>
          <div style={s.sectionLabel}>What went well</div>
          {whatWentWell.map((item, i) => (
            <div key={i} style={s.positiveItem}>
              <div style={s.checkBox}>✓</div>
              <div style={s.posText}>{item}</div>
            </div>
          ))}
        </div>
      )}

      {focusAreas.length > 0 && (
        <div style={s.section}>
          <div style={s.sectionLabel}>One thing to focus on this week</div>
          <div style={s.alertBox}>
            <div style={s.alertTitle}>
              {focusAreas[0].nutrient} — {focusAreas[0].gap}
            </div>
            <div style={s.alertBody}>
              {(focusAreas[0].food_fixes ?? []).join(" · ")}
            </div>
          </div>
        </div>
      )}

      {actions.length > 0 && (
        <div style={s.section}>
          <div style={s.sectionLabel}>Simple actions — next 7 days</div>
          {actions.map((a, i) => (
            <div key={i} style={s.actionItem}>
              <div style={s.actionNutrient}>{a.nutrient}</div>
              <div style={s.actionBody}>{(a.food_fixes ?? []).join(", ")}</div>
              {a.recipe && (
                <div style={s.actionRecipe}>Suggested: {a.recipe}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {featuredRecipe && (
        <div style={s.section}>
          <div style={s.sectionLabel}>This week's featured recipe</div>
          <div style={s.recipeRow}>
            <div style={s.recipeIcon}>🍽</div>
            <div style={{ flex: 1 }}>
              <div style={s.recipeName}>{featuredRecipe.name}</div>
              <div style={s.recipeWhy}>{featuredRecipe.reason}</div>
            </div>
          </div>
        </div>
      )}

      {gameReadiness && (
        <div style={s.section}>
          <div style={s.sectionLabel}>Game readiness</div>
          <div style={s.readinessText}>{gameReadiness}</div>
        </div>
      )}
    </div>
  );
}

const s = {
  card: {
    background: "#fff",
    borderRadius: "14px",
    border: "1px solid #dce8e0",
    overflow: "hidden",
  },
  header: {
    padding: "14px 16px 12px",
    borderBottom: "1px solid #dce8e0",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  title: {
    fontFamily: "'Nunito', sans-serif",
    fontSize: "16px",
    fontWeight: "800",
    color: "#1b3a2a",
  },
  headerSub: { fontSize: "11px", color: "#8aa898", marginTop: "2px" },
  gradeBlock: { textAlign: "center", flexShrink: 0 },
  grade: {
    fontFamily: "'Nunito', sans-serif",
    fontSize: "18px",
    fontWeight: "900",
    color: "#2d6a4f",
  },
  gradeSub: {
    fontSize: "10px",
    color: "#8aa898",
    textTransform: "uppercase",
    letterSpacing: ".06em",
  },
  loadingBody: { padding: "32px 16px", textAlign: "center" },
  spinner: {
    width: "32px",
    height: "32px",
    borderRadius: "50%",
    margin: "0 auto 12px",
    border: "3px solid #dce8e0",
    borderTopColor: "#2d6a4f",
    animation: "athfuelpath-spin 0.8s linear infinite",
  },
  loadingText: {
    fontSize: "14px",
    color: "#1b3a2a",
    fontWeight: "600",
    margin: "0 0 4px",
  },
  loadingSub: { fontSize: "12px", color: "#8aa898", margin: 0 },
  section: { padding: "12px 16px", borderBottom: "1px solid #f4f8f5" },
  sectionLabel: {
    fontSize: "11px",
    textTransform: "uppercase",
    letterSpacing: ".1em",
    color: "#8aa898",
    fontWeight: "600",
    marginBottom: "8px",
  },
  positiveItem: {
    display: "flex",
    alignItems: "flex-start",
    gap: "8px",
    marginBottom: "6px",
  },
  checkBox: {
    width: "20px",
    height: "20px",
    borderRadius: "6px",
    background: "rgba(45,106,79,.12)",
    color: "#2d6a4f",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "12px",
    fontWeight: "700",
    flexShrink: 0,
    marginTop: "1px",
  },
  posText: { fontSize: "13px", color: "#1b3a2a", lineHeight: "1.5" },
  alertBox: {
    background: "rgba(217,119,6,.06)",
    border: "1px solid rgba(217,119,6,.2)",
    borderRadius: "10px",
    padding: "10px 12px",
  },
  alertTitle: {
    fontSize: "13px",
    fontWeight: "700",
    color: "#b45309",
    marginBottom: "4px",
  },
  alertBody: { fontSize: "12px", color: "#4a6358", lineHeight: "1.5" },
  actionItem: {
    background: "#f4f8f5",
    borderRadius: "8px",
    padding: "10px",
    marginBottom: "6px",
  },
  actionNutrient: {
    fontSize: "12px",
    fontWeight: "700",
    color: "#2d6a4f",
    textTransform: "uppercase",
    letterSpacing: ".06em",
    marginBottom: "3px",
  },
  actionBody: { fontSize: "13px", color: "#1b3a2a", lineHeight: "1.5" },
  actionRecipe: {
    fontSize: "11px",
    color: "#8aa898",
    marginTop: "4px",
    fontStyle: "italic",
  },
  recipeRow: {
    display: "flex",
    gap: "10px",
    alignItems: "flex-start",
    background: "rgba(45,106,79,.06)",
    border: "1px solid rgba(45,106,79,.15)",
    borderRadius: "10px",
    padding: "10px 12px",
  },
  recipeIcon: { fontSize: "20px", flexShrink: 0 },
  recipeName: {
    fontSize: "13px",
    fontWeight: "700",
    color: "#1b3a2a",
    marginBottom: "2px",
  },
  recipeWhy: { fontSize: "12px", color: "#4a6358", lineHeight: "1.4" },
  readinessText: { fontSize: "13px", color: "#1b3a2a", lineHeight: "1.6" },
};
