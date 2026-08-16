import { useState, useEffect, useCallback } from "react";
import WeekNav from "./components/nutrition/WeekNav";
import WinHero from "./components/nutrition/WinHero";
import WeeklyHeatmap from "./components/nutrition/WeeklyHeatmap";
import ParentReport from "./components/nutrition/ParentReport";

const API = import.meta.env.VITE_API_URL ?? "";

function getWeekStart(isoDate) {
  const d = new Date(isoDate + "T12:00:00");
  const day = d.getDay(); // 0 = Sunday
  const diff = day === 0 ? -6 : 1 - day; // shift to Monday
  d.setDate(d.getDate() + diff);
  return d.toISOString().split("T")[0];
}

function addWeeks(weekStart, n) {
  const d = new Date(weekStart + "T12:00:00");
  d.setDate(d.getDate() + 7 * n);
  return d.toISOString().split("T")[0];
}

export default function NutritionDashboard({ athlete }) {
  const currentWeekStart = getWeekStart(new Date().toISOString().split("T")[0]);
  const [weekStart, setWeekStart] = useState(currentWeekStart);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const isCurrentWeek = weekStart === currentWeekStart;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(
        `${API}/api/athletes/${athlete.id}/weekly-summary?week_start=${weekStart}`
      );
      if (!res.ok) throw new Error("Failed to load weekly summary.");
      setSummary(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [athlete.id, weekStart]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div style={s.page}>
      <WeekNav
        weekStart={weekStart}
        weekEnd={summary?.week_end ?? weekStart}
        daysLogged={summary?.days_logged ?? 0}
        isCurrentWeek={isCurrentWeek}
        onPrev={() => setWeekStart((ws) => addWeeks(ws, -1))}
        onNext={() => {
          if (!isCurrentWeek) setWeekStart((ws) => addWeeks(ws, 1));
        }}
      />

      {loading && (
        <div style={s.center}>
          <p style={s.loadingText}>Loading week data…</p>
        </div>
      )}

      {!loading && error && (
        <div style={s.center}>
          <p style={{ color: "#b83a3a", fontSize: "14px" }}>{error}</p>
          <button style={s.retryBtn} onClick={load}>
            Retry
          </button>
        </div>
      )}

      {!loading && summary && (
        <div style={s.body}>
          <WinHero athlete={athlete} weekSummary={summary} />
          <WeeklyHeatmap days={summary.days} heatmap={summary.heatmap} />
          <ParentReport athleteId={athlete.id} weekStart={weekStart} />
          <p style={s.disclaimer}>
            AthFuelPath provides food education guidance — not medical nutrition
            therapy. Consult your physician or a licensed RDN for medical
            nutrition concerns.
          </p>
        </div>
      )}
    </div>
  );
}

const s = {
  page: {
    fontFamily: "'Nunito', 'DM Sans', sans-serif",
    background: "#f4f8f5",
    minHeight: "100vh",
  },
  body: {
    padding: "12px 12px 80px",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
  },
  center: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "48px 16px",
  },
  loadingText: { fontSize: "15px", color: "#4a6358" },
  retryBtn: {
    marginTop: "8px",
    padding: "8px 20px",
    borderRadius: "8px",
    background: "#2d6a4f",
    color: "#fff",
    border: "none",
    fontSize: "14px",
    fontWeight: "600",
    cursor: "pointer",
  },
  disclaimer: {
    textAlign: "center",
    fontSize: "12px",
    color: "#8aa898",
    lineHeight: "1.5",
    paddingTop: "8px",
  },
};
