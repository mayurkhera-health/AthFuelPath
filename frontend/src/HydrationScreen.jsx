import { useState, useEffect, useCallback } from "react";
import LoadingState from "./components/LoadingState";
import { LOADING_MESSAGES } from "./constants/loadingMessages";
import { useRotatingMessage } from "./hooks/useRotatingMessage";

const API = import.meta.env.VITE_API_URL ?? "";
const TODAY = new Date().toISOString().split("T")[0];

function deriveSweatProfile(athlete) {
  const age    = athlete.age || 13;
  const gender = (athlete.gender || "").toLowerCase();
  const level  = (athlete.competition_level || "").toLowerCase();

  let profile = age <= 11 ? "light" : age <= 13 ? "moderate" : "heavy";
  if (age >= 16 && gender.includes("boy")) profile = "very heavy";
  if (level === "elite" || level === "competitive") {
    profile = { light: "moderate", moderate: "heavy", heavy: "very heavy", "very heavy": "very heavy" }[profile];
  }
  return profile;
}

const SWEAT_LABEL = { light: "Light", moderate: "Moderate", heavy: "Heavy", "very heavy": "Very Heavy" };

function ResultBar({ label, value, max, unit, color }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  return (
    <div style={rb.wrap}>
      <div style={rb.row}>
        <span style={rb.label}>{label}</span>
        <span style={{ ...rb.value, color }}>{value}<span style={rb.unit}>{unit}</span></span>
      </div>
      <div style={rb.track}>
        <div style={{ ...rb.fill, width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}
const rb = {
  wrap: { marginBottom: "14px" },
  row: { display: "flex", justifyContent: "space-between", marginBottom: "5px" },
  label: { fontSize: "15px", fontWeight: "600", color: "#4a6358" },
  value: { fontSize: "17px", fontWeight: "800" },
  unit: { fontSize: "14px", fontWeight: "400", color: "#4a6358", marginLeft: "2px" },
  track: { height: "8px", background: "#dce8e0", borderRadius: "99px", overflow: "hidden" },
  fill: { height: "100%", borderRadius: "99px", transition: "width 0.5s ease" },
};

export default function HydrationScreen({ athlete }) {
  const [events, setEvents]     = useState([]);
  const [eventId, setEventId]   = useState("");
  const [city, setCity]         = useState("");
  const [manualMode, setManualMode] = useState(false);
  const [tempF, setTempF]       = useState(75);
  const [humidity, setHumidity] = useState(50);
  const [result, setResult]     = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [eventsLoading, setEventsLoading] = useState(true);

  const hydrationMsg = useRotatingMessage(LOADING_MESSAGES.hydration, { active: loading });

  const fetchEvents = useCallback(async () => {
    const res = await fetch(`${API}/api/events/athlete/${athlete.id}`);
    const all = res.ok ? await res.json() : [];
    // Show upcoming events (today and future)
    const upcoming = all.filter(e => e.event_date >= TODAY && e.event_type !== "rest")
                        .sort((a, b) => a.event_date.localeCompare(b.event_date));
    setEvents(upcoming);
    if (upcoming.length > 0) {
      setEventId(String(upcoming[0].id));
      setCity(upcoming[0].city || "");
    }
    setEventsLoading(false);
  }, [athlete.id]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  // Auto-fill city when event changes
  useEffect(() => {
    const ev = events.find(e => String(e.id) === eventId);
    if (ev) setCity(ev.city || "");
  }, [eventId, events]);

  async function handleCalculate() {
    if (!eventId) return setError("Please select an event.");
    setLoading(true); setError(""); setResult(null);

    if (manualMode) {
      // Build a local calc without hitting the weather API
      const ev = events.find(e => String(e.id) === eventId);
      if (!ev) { setError("Event not found."); setLoading(false); return; }
      const res = await calcManual(athlete, ev, tempF, humidity);
      setResult(res);
    } else {
      if (!city.trim()) { setError("Please enter a city for weather lookup."); setLoading(false); return; }
      const res = await fetch(`${API}/api/nutrition/sweat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ athlete_id: athlete.id, event_id: parseInt(eventId), city: city.trim() }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || "Calculation failed."); setLoading(false); return; }
      // If weather API failed, switch to manual result with a note
      if (data.weather_temp_f === null) {
        setManualMode(true);
        const ev = events.find(e => String(e.id) === eventId);
        const manual = await calcManual(athlete, ev, tempF, humidity);
        setResult({ ...manual, weather_note: "Weather API not configured — showing estimate based on manual inputs." });
      } else {
        setResult(data);
      }
    }
    setLoading(false);
  }

  const selectedEvent = events.find(e => String(e.id) === eventId);
  const eventDate = selectedEvent
    ? new Date(selectedEvent.event_date + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
    : "";

  return (
    <div>
      <h2 style={s.title}>Sweat & Hydration Calculator</h2>
      <p style={s.subtitle}>
        Science-based hydration plan for {athlete.first_name} based on age, body weight, competition level, event type, and weather conditions.
      </p>

      {/* Athlete summary */}
      <div style={s.athleteCard}>
        <div style={s.athleteRow}>
          <span style={s.athleteStat}><b>{athlete.weight_lbs} lbs</b><span style={s.athleteStatLabel}>Weight</span></span>
          <span style={s.athleteStat}><b>{SWEAT_LABEL[deriveSweatProfile(athlete)]}</b><span style={s.athleteStatLabel}>Sweat Profile</span></span>
          <span style={s.athleteStat}><b>{athlete.age} yrs</b><span style={s.athleteStatLabel}>Age</span></span>
        </div>
        <p style={s.athleteNote}>
          Sweat profile is automatically calculated from age, gender, and competition level.
        </p>
      </div>

      {/* Event selector */}
      <div style={s.section}>
        <div style={s.sectionTitle}>Select Event</div>
        {eventsLoading ? (
          <LoadingState message="Loading events…" subtle />
        ) : events.length === 0 ? (
          <div style={s.noEvents}>
            No upcoming events found. Add games or practices in the Schedule tab first.
          </div>
        ) : (
          <div style={s.eventGrid}>
            {events.slice(0, 6).map(ev => (
              <button
                key={ev.id}
                style={{ ...s.eventChip, ...(String(ev.id) === eventId ? s.eventChipActive : {}) }}
                onClick={() => setEventId(String(ev.id))}
              >
                <div style={s.eventChipType}>{ev.event_type}</div>
                <div style={s.eventChipName}>{ev.event_name.length > 20 ? ev.event_name.slice(0,19) + "…" : ev.event_name}</div>
                <div style={s.eventChipDate}>
                  {new Date(ev.event_date + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  {ev.start_time ? ` · ${ev.start_time}` : ""}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Weather input */}
      {events.length > 0 && (
        <div style={s.section}>
          <div style={s.sectionHeader}>
            <div style={s.sectionTitle}>Weather Conditions</div>
            <button style={s.modeToggle} onClick={() => { setManualMode(!manualMode); setResult(null); }}>
              {manualMode ? "Use city lookup" : "Enter manually"}
            </button>
          </div>

          {!manualMode ? (
            <div>
              <label style={s.label}>City / Location</label>
              <input
                style={s.input}
                placeholder="e.g. Dallas, TX"
                value={city}
                onChange={e => setCity(e.target.value)}
              />
              <p style={s.hint}>AthFuelPath will fetch live weather for this city to calculate sweat loss.</p>
            </div>
          ) : (
            <div>
              <p style={s.hint}>Enter estimated conditions for the event location.</p>
              <div style={s.sliderRow}>
                <div style={s.sliderGroup}>
                  <div style={s.sliderLabel}>
                    <span>Temperature</span>
                    <span style={s.sliderVal}>{tempF}°F</span>
                  </div>
                  <input type="range" min="40" max="115" value={tempF} onChange={e => setTempF(parseInt(e.target.value))} style={s.slider} />
                  <div style={s.sliderEnds}><span>40°F</span><span>115°F</span></div>
                </div>
                <div style={s.sliderGroup}>
                  <div style={s.sliderLabel}>
                    <span>Humidity</span>
                    <span style={s.sliderVal}>{humidity}%</span>
                  </div>
                  <input type="range" min="0" max="100" value={humidity} onChange={e => setHumidity(parseInt(e.target.value))} style={s.slider} />
                  <div style={s.sliderEnds}><span>0%</span><span>100%</span></div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Calculate button */}
      {events.length > 0 && (
        <button style={s.calcBtn} onClick={handleCalculate} disabled={loading || !eventId}>
          {loading ? "Calculating…" : "Calculate Hydration Plan →"}
        </button>
      )}

      {error && <div style={s.errorBox}>{error}</div>}

      {loading && <LoadingState message={hydrationMsg} />}

      {/* Results */}
      {result && (
        <div style={s.results}>
          {/* Event + weather banner */}
          <div style={s.resultHeader}>
            <div style={s.resultTitle}>Hydration Plan</div>
            <div style={s.resultEvent}>{selectedEvent?.event_name} · {eventDate}</div>
            {result.weather_temp_f && (
              <div style={s.weatherBadge}>
                🌡 {Math.round(result.weather_temp_f)}°F · 💧 {result.weather_humidity}% humidity
              </div>
            )}
            {result.weather_note && <div style={s.weatherNote}>{result.weather_note}</div>}
          </div>

          {/* Key numbers */}
          <div style={s.numbersRow}>
            <div style={s.numberCard}>
              <div style={s.numberVal}>{result.hydration_oz_during}</div>
              <div style={s.numberLabel}>oz during event</div>
            </div>
            <div style={s.numberCard}>
              <div style={s.numberVal}>{Math.round(result.hydration_oz_during / 8)}</div>
              <div style={s.numberLabel}>cups of water</div>
            </div>
            <div style={s.numberCard}>
              <div style={s.numberVal}>{result.sweat_loss_liters}</div>
              <div style={s.numberLabel}>liters sweat lost</div>
            </div>
          </div>

          {/* Bar visualization */}
          <ResultBar label="During Event" value={result.hydration_oz_during} max={64} unit=" oz" color="#0ea5e9" />
          <ResultBar label="Pre-Event (2hrs before)" value={16} max={64} unit=" oz" color="#2d6a4f" />
          <ResultBar label="Post-Event Recovery" value={24} max={64} unit=" oz" color="#d97706" />

          {/* Electrolytes */}
          <div style={{ ...s.electCard, background: result.electrolytes_needed ? "#fffbeb" : "#f0fdf4", borderColor: result.electrolytes_needed ? "#fde68a" : "#b0e8c8" }}>
            <div style={s.electHeader}>
              <span style={s.electIcon}>{result.electrolytes_needed ? "⚡" : "💧"}</span>
              <span style={{ ...s.electTitle, color: result.electrolytes_needed ? "#92400e" : "#2d6a4f" }}>
                {result.electrolytes_needed ? "Electrolytes Recommended" : "Water Only — No Sports Drink Needed"}
              </span>
            </div>
            {result.electrolyte_reason && (
              <div style={s.electReason}>Reason: {result.electrolyte_reason}</div>
            )}
          </div>

          {/* Recommendations */}
          <div style={s.recsCard}>
            <div style={s.recsTitle}>Recommendations</div>
            {result.recommendations.map((r, i) => (
              <div key={i} style={s.recRow}>
                <span style={s.recDot}>•</span>
                <span style={s.recText}>{r}</span>
              </div>
            ))}
          </div>

          {/* Hydration timeline */}
          <div style={s.timelineCard}>
            <div style={s.recsTitle}>Hydration Timeline</div>
            {[
              { time: "Night before", tip: "Drink 16–24 oz with dinner. Urine should be pale yellow.", icon: "🌙" },
              { time: "Morning of event", tip: "Drink 16 oz with breakfast. Add electrolytes if hot day.", icon: "☀️" },
              { time: "2hrs before", tip: "16 oz of water. Eat sodium-containing foods (pretzels, crackers).", icon: "⏰" },
              { time: "During event", tip: `6–8 oz every 20 minutes = ~${result.hydration_oz_during} oz total.${result.electrolytes_needed ? " Use natural sports drink." : " Water is fine."}`, icon: "⚽" },
              { time: "Within 30min after", tip: "24 oz of water or chocolate milk. Aim to replace 150% of sweat lost.", icon: "🏁" },
            ].map((item, i) => (
              <div key={i} style={s.timelineRow}>
                <span style={s.timelineIcon}>{item.icon}</span>
                <div>
                  <div style={s.timelineTime}>{item.time}</div>
                  <div style={s.timelineTip}>{item.tip}</div>
                </div>
              </div>
            ))}
          </div>

          <p style={s.disclaimer}>
            Science: Everett MD 2025 · ACSM 2016 · Boston Children's Hospital RDN · AAP guidelines<br/>
            AthFuelPath provides educational food guidance — not medical nutrition therapy.
          </p>
        </div>
      )}
    </div>
  );
}

// Local calculation used when weather API isn't configured
async function calcManual(athlete, event, tempF, humidity) {
  const wt_kg = athlete.weight_lbs * 0.453592;
  const event_type = (event.event_type || "").toLowerCase();
  const base_rate = event_type.includes("game") || event_type.includes("tournament") ? 1.2
                  : event_type.includes("practice") ? 1.0 : 0.5;
  const sweat_map = { light: 0.7, moderate: 1.0, heavy: 1.3, "very heavy": 1.6 };
  const profile_mult = sweat_map[deriveSweatProfile(athlete)] || 1.0;
  const temp_mult = tempF > 95 ? 1.40 : tempF > 85 ? 1.25 : tempF > 75 ? 1.10 : 1.0;
  const hum_mult  = humidity > 80 ? 1.30 : humidity > 60 ? 1.15 : 1.0;
  const duration  = event.duration_hours || 1.5;
  const sweat_rate = base_rate * profile_mult * temp_mult * hum_mult;
  const total_liters = sweat_rate * duration;
  const hydration_oz = Math.round(total_liters * 33.8);

  const reasons = [];
  if (tempF > 80)    reasons.push(`Temperature ${tempF}°F`);
  if (humidity > 70) reasons.push(`Humidity ${humidity}%`);
  if (duration > 1)  reasons.push(`Duration ${duration}hrs`);
  if (event_type.includes("tournament")) reasons.push("Tournament day");
  const electrolytes_needed = reasons.length > 0;

  const recommendations = [];
  if (electrolytes_needed) {
    recommendations.push("Natural sports drink — NO artificial dyes (Red #40, Yellow #5, Yellow #6)");
    if (tempF > 80) recommendations.push("Add a pinch of salt to the pre-event meal");
  } else {
    recommendations.push("Plain water is sufficient — no sports drink needed");
  }
  recommendations.push("Drink 6–8 oz every 20 minutes during activity");

  return {
    sweat_loss_liters: Math.round(total_liters * 100) / 100,
    hydration_oz_during: hydration_oz,
    electrolytes_needed,
    electrolyte_reason: reasons.join(", ") || null,
    weather_temp_f: tempF,
    weather_humidity: humidity,
    recommendations,
  };
}

const s = {
  title: { fontSize: "19px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a", margin: "0 0 4px" },
  subtitle: { fontSize: "15px", color: "#4a6358", marginBottom: "20px", lineHeight: 1.5 },

  athleteCard: { background: "#f0fdf4", border: "1.5px solid #bbf7d0", borderRadius: "12px", padding: "14px 18px", marginBottom: "16px" },
  athleteRow: { display: "flex", gap: "24px", marginBottom: "6px" },
  athleteStat: { display: "flex", flexDirection: "column" },
  athleteStatLabel: { fontSize: "16px", color: "#4a6358", marginTop: "2px" },
  athleteNote: { fontSize: "16px", color: "#4a6358", margin: 0 },

  section: { background: "#f4f8f5", border: "1.5px solid #e5e7eb", borderRadius: "12px", padding: "16px 18px", marginBottom: "14px" },
  sectionHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" },
  sectionTitle: { fontSize: "15px", fontWeight: "700", color: "#4a6358", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "12px" },
  modeToggle: { background: "none", border: "1.5px solid #d1d5db", borderRadius: "6px", padding: "4px 10px", fontSize: "14px", fontWeight: "600", color: "#4a6358", cursor: "pointer" },

  eventGrid: { display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "8px" },
  eventChip: { background: "#fff", border: "1.5px solid #e5e7eb", borderRadius: "10px", padding: "10px 12px", cursor: "pointer", textAlign: "left" },
  eventChipActive: { background: "#f0fdf4", borderColor: "#2d6a4f" },
  eventChipType: { fontSize: "15px", fontWeight: "700", color: "#2d6a4f", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "3px" },
  eventChipName: { fontSize: "15px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a", marginBottom: "2px" },
  eventChipDate: { fontSize: "16px", color: "#4a6358" },
  noEvents: { fontSize: "15px", color: "#4a6358", textAlign: "center", padding: "12px 0" },

  label: { display: "block", fontSize: "14px", fontWeight: "600", color: "#4a6358", marginBottom: "6px" },
  input: { width: "100%", padding: "9px 12px", border: "1.5px solid #d1d5db", borderRadius: "8px", fontSize: "16px", boxSizing: "border-box", outline: "none", background: "#fff" },
  hint: { fontSize: "14px", color: "#4a6358", marginTop: "6px" },

  sliderRow: { display: "flex", gap: "20px", flexWrap: "wrap" },
  sliderGroup: { flex: "1 1 200px" },
  sliderLabel: { display: "flex", justifyContent: "space-between", fontSize: "15px", fontWeight: "600", color: "#4a6358", marginBottom: "6px" },
  sliderVal: { color: "#2d6a4f" },
  slider: { width: "100%", accentColor: "#2d6a4f" },
  sliderEnds: { display: "flex", justifyContent: "space-between", fontSize: "16px", color: "#4a6358", marginTop: "2px" },

  calcBtn: { width: "100%", padding: "13px", background: "linear-gradient(135deg, #2d6a4f, #52b788)", color: "#fff", border: "none", borderRadius: "10px", fontSize: "16px", fontWeight: "700", cursor: "pointer", marginBottom: "16px" },
  errorBox: { background: "#fef2f2", border: "1.5px solid #fecaca", borderRadius: "8px", padding: "10px 14px", fontSize: "15px", color: "#dc2626", marginBottom: "12px" },

  results: { background: "#fff", border: "1.5px solid #e5e7eb", borderRadius: "14px", padding: "20px", marginTop: "4px" },
  resultHeader: { marginBottom: "20px" },
  resultTitle: { fontSize: "17px", fontWeight: "800", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a", marginBottom: "2px" },
  resultEvent: { fontSize: "15px", color: "#4a6358", marginBottom: "6px" },
  weatherBadge: { display: "inline-block", background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: "99px", padding: "3px 10px", fontSize: "14px", color: "#0369a1", fontWeight: "600" },
  weatherNote: { fontSize: "14px", color: "#d97706", marginTop: "6px" },

  numbersRow: { display: "flex", gap: "10px", marginBottom: "20px" },
  numberCard: { flex: 1, background: "#f0fdf4", borderRadius: "10px", padding: "14px", textAlign: "center" },
  numberVal: { fontSize: "31px", fontWeight: "800", color: "#2d6a4f", lineHeight: 1 },
  numberLabel: { fontSize: "16px", color: "#4a6358", marginTop: "4px" },

  electCard: { border: "1.5px solid", borderRadius: "10px", padding: "14px 16px", marginBottom: "14px" },
  electHeader: { display: "flex", alignItems: "center", gap: "8px" },
  electIcon: { fontSize: "19px" },
  electTitle: { fontSize: "16px", fontWeight: "700" },
  electReason: { fontSize: "14px", color: "#4a6358", marginTop: "6px" },

  recsCard: { background: "#f4f8f5", borderRadius: "10px", padding: "14px 16px", marginBottom: "14px" },
  recsTitle: { fontSize: "15px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", color: "#1b3a2a", marginBottom: "10px" },
  recRow: { display: "flex", gap: "8px", marginBottom: "6px", alignItems: "flex-start" },
  recDot: { color: "#2d6a4f", fontWeight: "800", flexShrink: 0 },
  recText: { fontSize: "15px", color: "#4a6358", lineHeight: 1.5 },

  timelineCard: { background: "#f4f8f5", borderRadius: "10px", padding: "14px 16px", marginBottom: "14px" },
  timelineRow: { display: "flex", gap: "12px", marginBottom: "10px", alignItems: "flex-start" },
  timelineIcon: { fontSize: "19px", flexShrink: 0 },
  timelineTime: { fontSize: "14px", fontWeight: "700", color: "#2d6a4f", marginBottom: "2px" },
  timelineTip: { fontSize: "14px", color: "#4a6358", lineHeight: 1.5 },

  disclaimer: { fontSize: "16px", color: "#8aa898", textAlign: "center", marginTop: "8px", lineHeight: 1.6 },
};
