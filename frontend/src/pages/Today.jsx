import { useState, useEffect, useCallback } from "react";
import BroadcastCard       from "../components/today/BroadcastCard";
import PerformanceForecast from "../components/today/PerformanceForecast";
import DailyMission        from "../components/today/DailyMission";
import ScienceEdge         from "../components/today/ScienceEdge";
import QuickRow            from "../components/today/QuickRow";
import Toast, { useToast } from "../components/today/Toast";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";

const API = import.meta.env.VITE_API_URL ?? "";

export default function Today({ athlete, onNavigate }) {
  const [summary, setSummary]     = useState(null);
  const [loading, setLoading]     = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [waterCups, setWaterCups] = useState(0);
  const { message: toastMsg, showToast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const res = await fetch(`${API}/api/athletes/${athlete.id}/daily-summary`);
      if (res.ok) {
        const d = await res.json();
        setSummary(d);
        setWaterCups(d.water_cups ?? 0);
      }
    } catch (e) { void e; setLoadError(true); }
    finally { setLoading(false); }
  }, [athlete.id]);

  useEffect(() => { void load(); }, [load, reloadKey]);

  useEffect(() => {
    const onVisible = () => { if (!document.hidden) load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [load]);

  async function handleWaterUpdate(cups) {
    setWaterCups(cups);
    try {
      await fetch(`${API}/api/water-log/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ athlete_id: athlete.id, cups }),
      });
    } catch (e) { void e; }
  }

  if (loading) return <LoadingState message="Loading today's briefing…" />;
  if (loadError) return <ErrorState message="Couldn't load today's briefing." onRetry={() => setReloadKey((k) => k + 1)} />;

  const events       = summary?.events ?? [];
  const eventType    = summary?.event_type ?? "rest";

  function getEventLabel(et) {
    return { game: "Game Day", tournament: "Tournament Day", practice: "Practice Day",
             strength: "Strength Day", pregame_day: "Pre-Game Day",
             recovery: "Recovery Day", rest: "Rest Day" }[et] || "Today";
  }
  const tl           = summary?.traffic_light ?? {};
  const fuelScore    = tl.daily_fuel_score ?? 0;
  const targets      = summary?.targets ?? {};
  const targetCups   = Math.round((targets.hydration_oz_min ?? 64) / 8);
  const missionItems = summary?.mission_items ?? [];
  const forecast     = summary?.performance_forecast ?? null;

  return (
    <div style={s.page}>
      <BroadcastCard
        athlete={summary?.athlete ?? { first_name: athlete.first_name }}
        events={events}
        trafficLight={tl}
        fuelScore={fuelScore}
        onNavigateMealPlan={() => onNavigate("meal-plan")}
      />

      <div style={s.body}>
        <PerformanceForecast forecast={forecast} />

        <DailyMission
          missionItems={missionItems}
          eventType={eventType}
          eventLabel={getEventLabel(eventType)}
          date={summary?.date}
          athleteId={athlete.id}
          onToast={showToast}
        />

        <ScienceEdge
          trafficLight={tl}
          onToast={showToast}
        />

        <QuickRow
          waterCups={waterCups}
          targetCups={targetCups}
          caloriesLogged={tl.calories?.logged ?? 0}
          caloriesTarget={tl.calories?.target ?? 0}
          athleteId={athlete.id}
          onWaterUpdate={handleWaterUpdate}
        />

        <div style={s.logWrap}>
          <div style={s.logHint}>
            Tap <strong>Photo</strong> or <strong>Say it</strong> on any mission item to log your fuel.
          </div>
        </div>

        <p style={s.disclaimer}>
          AthFuelPath provides food education guidance — not medical nutrition therapy.
          Consult your physician or a licensed RDN for medical nutrition concerns.
        </p>
      </div>

      <Toast message={toastMsg} />
    </div>
  );
}

const s = {
  page:       { fontFamily: "'Nunito', 'DM Sans', sans-serif", paddingBottom: "8px", background: "#f8faf9", minHeight: "100vh" },
  body:       { padding: "0 12px" },
  loadWrap:   { display: "flex", flexDirection: "column", alignItems: "center", gap: "14px", padding: "60px 0" },
  spinner:    { width: "30px", height: "30px", border: "3px solid #dce8e0", borderTopColor: "#2d6a4f", borderRadius: "50%", animation: "spin 0.7s linear infinite" },
  loadText:   { fontSize: "18px", color: "#4a6358", fontFamily: "'DM Sans', sans-serif" },
  logWrap:    { paddingTop: "6px" },
  logHint:    { fontSize: "13px", color: "#8aa898", textAlign: "center", lineHeight: "1.5", padding: "4px 0 8px" },
  disclaimer: { textAlign: "center", fontSize: "15px", color: "#4a6358", lineHeight: "1.5", fontWeight: "400", padding: "10px 0 0" },
};
