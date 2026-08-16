import { useState, useEffect, useCallback, useMemo } from "react";
import LoadingState from "./components/LoadingState";
import ErrorState from "./components/ErrorState";

const API = import.meta.env.VITE_API_URL ?? "";
const TODAY = new Date().toISOString().split("T")[0];

// ── Sport / day-type photos (Unsplash, free) ─────────────────────────────────
const DAY_PHOTO = {
  game:       "https://images.unsplash.com/photo-1579952363873-27f3bade9f55?w=900&q=80",
  tournament: "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=900&q=80",
  practice:   "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=900&q=80",
  training:   "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=900&q=80",
  strength:   "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=900&q=80",
  rest:       "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=900&q=80",
};

// ── Food thumbnail photos per meal label ─────────────────────────────────────
const MEAL_PHOTO = {
  "Breakfast":               "https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=160&q=80",
  "Tournament Breakfast":    "https://images.unsplash.com/photo-1528207776546-365bb710ee93?w=160&q=80",
  "High-Carb Breakfast":     "https://images.unsplash.com/photo-1528207776546-365bb710ee93?w=160&q=80",
  "Pre-Game Meal":           "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?w=160&q=80",
  "Pre-Practice Meal":       "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=160&q=80",
  "Pre-Strength Meal":       "https://images.unsplash.com/photo-1532550907401-a500c9a57435?w=160&q=80",
  "Pre-Game Snack":          "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=160&q=80",
  "Top-Up Snack":            "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=160&q=80",
  "Pre-Game 2 Top-Up":       "https://images.unsplash.com/photo-1490474418585-ba9bad8fd0ea?w=160&q=80",
  "Recovery Window":         "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=160&q=80",
  "Recovery Snack":          "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=160&q=80",
  "Post-Workout Window":     "https://images.unsplash.com/photo-1563636619-e9143da7973b?w=160&q=80",
  "Between-Games Recovery":  "https://images.unsplash.com/photo-1490474418585-ba9bad8fd0ea?w=160&q=80",
  "Lunch":                   "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=160&q=80",
  "Dinner":                  "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=160&q=80",
  "Tournament Dinner":       "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?w=160&q=80",
  "Snack":                   "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=160&q=80",
  "Bedtime Snack":           "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=160&q=80",
};

// ── Day config ────────────────────────────────────────────────────────────────
const DAY_CFG = {
  game:       { label: "Game Day",        emoji: "⚽", color: "#c05a4a", light: "#fdf2f0", grad: "linear-gradient(135deg,#8b3a2c 0%,#c05a4a 100%)" },
  tournament: { label: "Tournament Day",  emoji: "🏆", color: "#7e6ab5", light: "#f4f1fb", grad: "linear-gradient(135deg,#4a3980 0%,#7e6ab5 100%)" },
  practice:   { label: "Practice Day",    emoji: "🏃", color: "#c8903a", light: "#fdf5e7", grad: "linear-gradient(135deg,#8a5e1a 0%,#c8903a 100%)" },
  training:   { label: "Training Day",    emoji: "💪", color: "#c8903a", light: "#fdf5e7", grad: "linear-gradient(135deg,#8a5e1a 0%,#c8903a 100%)" },
  strength:   { label: "Strength Day",    emoji: "🏋️", color: "#4a8fc4", light: "#eef5fb", grad: "linear-gradient(135deg,#2a5a88 0%,#4a8fc4 100%)" },
  rest:       { label: "Rest & Recovery", emoji: "🌿", color: "#2d6a4f", light: "#f0faf4", grad: "linear-gradient(135deg,#1b4332 0%,#2d6a4f 100%)" },
};

// ── Meal macros ───────────────────────────────────────────────────────────────
const MACROS = {
  "Oatmeal + Eggs + OJ":         { calories: 480, carbs_g: 68, protein_g: 22, fat_g: 14 },
  "Power Pasta Bowl":             { calories: 650, carbs_g: 85, protein_g: 45, fat_g: 12 },
  "Banana + Peanut Butter":       { calories: 280, carbs_g: 36, protein_g:  8, fat_g: 12 },
  "Chocolate Milk + Banana":      { calories: 380, carbs_g: 62, protein_g: 17, fat_g:  5 },
  "Brown Rice Salmon Bowl":       { calories: 580, carbs_g: 72, protein_g: 38, fat_g: 18 },
  "High-Carb Pancakes + Eggs":    { calories: 680, carbs_g: 95, protein_g: 28, fat_g: 14 },
  "Banana + Honey":               { calories: 200, carbs_g: 52, protein_g:  1, fat_g:  0 },
  "Crackers + Peanut Butter":     { calories: 290, carbs_g: 38, protein_g: 10, fat_g: 11 },
  "Tournament Recovery Pasta":    { calories: 720, carbs_g: 82, protein_g: 48, fat_g: 16 },
  "Greek Yogurt + Berries":       { calories: 250, carbs_g: 30, protein_g: 20, fat_g:  4 },
  "Turkey Wrap + Milk":           { calories: 520, carbs_g: 65, protein_g: 38, fat_g: 14 },
  "Chicken + Brown Rice + Veg":   { calories: 580, carbs_g: 62, protein_g: 46, fat_g: 14 },
  "Eggs + Toast + Greek Yogurt":  { calories: 480, carbs_g: 44, protein_g: 34, fat_g: 16 },
  "Greek Yogurt + Banana":        { calories: 280, carbs_g: 42, protein_g: 20, fat_g:  3 },
  "Strength Day Protein Plate":   { calories: 640, carbs_g: 60, protein_g: 52, fat_g: 12 },
  "Cottage Cheese + Honey":       { calories: 240, carbs_g: 26, protein_g: 26, fat_g:  4 },
  "Eggs + Berries + Toast":       { calories: 420, carbs_g: 48, protein_g: 26, fat_g: 14 },
  "Salmon + Grain Bowl":          { calories: 520, carbs_g: 52, protein_g: 38, fat_g: 16 },
  "Almonds + Berries":            { calories: 180, carbs_g: 16, protein_g:  6, fat_g: 12 },
  "Iron-Boost Hummus Plate":      { calories: 420, carbs_g: 52, protein_g: 18, fat_g: 14 },
  "Cottage Cheese + Pineapple":   { calories: 250, carbs_g: 28, protein_g: 28, fat_g:  4 },
};

// ── Schedule builder ──────────────────────────────────────────────────────────
function buildSchedule(eventType, startTimeStr, durationHours) {
  const dur = (durationHours || 1.5) * 60;
  function at(h, m = 0) { const d = new Date(); d.setHours(h, m, 0, 0); return d; }
  let anchor = null;
  if (startTimeStr) { const [h, m] = startTimeStr.split(":").map(Number); anchor = at(h, m); }
  function fromAnchor(mins, dh = 16) { return new Date((anchor || at(dh)).getTime() + mins * 60_000); }
  const slot = (time, icon, label, meal, tip = null, urgent = false) =>
    ({ time, icon, label, meal, kcal: MACROS[meal]?.calories, tip, urgent, isMarker: false });
  const marker = (time, icon, label) => ({ time, icon, label, isMarker: true });

  switch (eventType) {
    case "game": return [
      slot(at(7),              "🌅", "Breakfast",       "Oatmeal + Eggs + OJ",      "Complex carbs + protein to start the day"),
      slot(fromAnchor(-210),   "🍝", "Pre-Game Meal",   "Power Pasta Bowl",          "HIGH carbs · LOW fat & fiber · Familiar foods only"),
      slot(fromAnchor(-60),    "🍌", "Pre-Game Snack",  "Banana + Peanut Butter",    "Easy-digest carbs only · No heavy food"),
      marker(anchor || at(16), "⚽", "KICKOFF"),
      slot(fromAnchor(dur+20), "🥛", "Recovery Window", "Chocolate Milk + Banana",   "3:1 carb:protein — key 30-min recovery window", true),
      slot(at(19),             "🍽️", "Dinner",          "Brown Rice Salmon Bowl",    "Full recovery meal"),
    ];
    case "tournament": return [
      slot(at(7),                  "🥞", "Tournament Breakfast",  "High-Carb Pancakes + Eggs", "Biggest carb meal of the day"),
      slot(fromAnchor(-60, 9),     "🍌", "Pre-Game Snack",        "Banana + Honey",            "Before every game"),
      marker(anchor || at(9),      "🏆", "GAME 1"),
      slot(fromAnchor(dur+15, 9),  "🥛", "Between-Games Recovery","Chocolate Milk + Banana",   "Refuel immediately — don't wait", true),
      slot(fromAnchor(dur+105, 9), "🍌", "Pre-Game 2 Top-Up",     "Crackers + Peanut Butter",  "60 min before next game"),
      marker(fromAnchor(dur+150, 9),"🏆","GAME 2"),
      slot(at(19),                 "🍝", "Tournament Dinner",      "Tournament Recovery Pasta", "Rebuild glycogen for tomorrow"),
      slot(at(21, 30),             "🌙", "Bedtime Snack",          "Greek Yogurt + Berries",    "Casein protein repairs muscles overnight"),
    ];
    case "practice": case "training": return [
      slot(at(7),              "🌅", "Breakfast",         "Oatmeal + Eggs + OJ",      "Energy baseline for the whole day"),
      slot(fromAnchor(-150),   "🍗", "Pre-Practice Meal", "Turkey Wrap + Milk",        "2.5 hrs to digest · Complex carbs + protein"),
      slot(fromAnchor(-45),    "🍌", "Top-Up Snack",      "Banana + Peanut Butter",    "Only if hungry — keep it light"),
      marker(anchor || at(16), "🏃", eventType === "training" ? "TRAINING" : "PRACTICE"),
      slot(fromAnchor(dur+15), "🥛", "Recovery Snack",    "Chocolate Milk + Banana",   "30-min window — muscle repair starts here", true),
      slot(new Date(Math.max(fromAnchor(dur+90).getTime(), at(18,30).getTime())),
                               "🍽️", "Dinner",            "Chicken + Brown Rice + Veg","Full recovery meal"),
      slot(at(21, 30),         "🌙", "Bedtime Snack",     "Greek Yogurt + Berries",    "Casein protein — repairs muscles overnight"),
    ];
    case "strength": return [
      slot(at(7),               "🥚", "Breakfast",           "Eggs + Toast + Greek Yogurt","Protein-rich start — strength days need it"),
      slot(fromAnchor(-90, 15), "🍗", "Pre-Strength Meal",   "Turkey Wrap + Milk",         "90 min to digest · Moderate carbs + protein"),
      marker(anchor || at(15),  "🏋️", "STRENGTH TRAINING"),
      slot(fromAnchor(dur+5,15),"🥛", "Post-Workout Window", "Greek Yogurt + Banana",      "20–30g protein within 30 min — non-negotiable", true),
      slot(at(19),              "🍽️", "Dinner",              "Strength Day Protein Plate", "Highest protein meal of the week"),
      slot(at(21, 30),          "🌙", "Bedtime Snack",       "Cottage Cheese + Honey",     "Casein — muscle synthesis runs all night"),
    ];
    default: return [
      slot(at(7, 30),  "🫐", "Breakfast",    "Eggs + Berries + Toast",    "Anti-inflammatory foods speed recovery"),
      slot(at(12),     "🥗", "Lunch",         "Salmon + Grain Bowl",       "Keep protein high — recovery continues 48 hrs"),
      slot(at(15),     "🥜", "Snack",          "Almonds + Berries",        "Antioxidants reduce inflammation"),
      slot(at(18, 30), "🍽️", "Dinner",        "Iron-Boost Hummus Plate",  "Iron + calcium focus on rest days"),
      slot(at(21, 30), "🌙", "Bedtime Snack", "Cottage Cheese + Pineapple","Casein protein — recovery doesn't stop on rest days"),
    ];
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt     = d => d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
const cdStr   = t => { const d = t - Date.now(); if (d <= 0) return null; const h = Math.floor(d/3_600_000), m = Math.floor((d%3_600_000)/60_000); return h > 0 ? `${h}h ${m}m` : `${m}m`; };
const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };
const scoreColor = s => s >= 90 ? "#2d6a4f" : s >= 75 ? "#d97706" : "#b45309";
const scoreLabel = s => s >= 90 ? "Elite Fueler" : s >= 75 ? "Game Ready" : s >= 50 ? "Building" : "Power Up";
const scoreEmoji = s => s >= 90 ? "🔥" : s >= 75 ? "✅" : s >= 50 ? "📈" : "⚠️";

// ── Event Hero ────────────────────────────────────────────────────────────────
function EventHero({ event, dayType, athlete }) {
  const day   = DAY_CFG[dayType] || DAY_CFG.rest;
  const photo = DAY_PHOTO[dayType] || DAY_PHOTO.rest;
  const eventTime = event?.start_time ? (() => {
    const [h, m] = event.start_time.split(":").map(Number);
    const d = new Date(); d.setHours(h, m, 0, 0); return d;
  })() : null;
  const cd = eventTime ? cdStr(eventTime) : null;
  const inProgress = eventTime && !cd && (Date.now() - eventTime.getTime()) < (event?.duration_hours || 1.5) * 3_600_000;
  const complete   = eventTime && !cd && !inProgress;

  return (
    <div style={hero.wrap}>
      <img src={photo} alt={day.label} style={hero.img} loading="lazy" />
      {/* dark tint */}
      <div style={hero.tint} />
      {/* bottom gradient so text is readable */}
      <div style={hero.fade} />

      <div style={hero.content}>
        {/* Top row — greeting + badge */}
        <div style={hero.topRow}>
          <div style={hero.greeting}>{greeting()}, {athlete.first_name} 👋</div>
          <div style={{ ...hero.badge, background: day.color }}>{day.emoji} {day.label}</div>
        </div>

        {/* Event name */}
        <div style={hero.eventName}>
          {event?.event_name || `${day.label} — No events`}
        </div>
        {event?.start_time && (
          <div style={hero.eventMeta}>
            Today · {fmt(eventTime)}{event.city ? ` · ${event.city}` : ""}
          </div>
        )}

        {/* Countdown chip */}
        {eventTime && (
          <div style={hero.chipRow}>
            {cd
              ? <div style={hero.chip}>⏱ Kickoff in <strong>{cd}</strong></div>
              : inProgress
              ? <div style={{ ...hero.chip, background: "rgba(16,185,129,0.9)" }}>🟢 In Progress</div>
              : complete
              ? <div style={{ ...hero.chip, background: "rgba(100,116,139,0.9)" }}>✓ Complete</div>
              : null
            }
          </div>
        )}
      </div>
    </div>
  );
}
const hero = {
  wrap:      { position: "relative", borderRadius: "18px", overflow: "hidden", height: "200px", marginBottom: "20px" },
  img:       { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" },
  tint:      { position: "absolute", inset: 0, background: "rgba(0,0,0,0.45)" },
  fade:      { position: "absolute", inset: 0, background: "linear-gradient(to top, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0) 50%)" },
  content:   { position: "relative", zIndex: 1, padding: "16px 18px", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between" },
  topRow:    { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "8px" },
  greeting:  { fontSize: "19px", fontWeight: "600", color: "rgba(255,255,255,0.85)" },
  badge:     { fontSize: "16px", fontWeight: "800", color: "#fff", padding: "4px 10px", borderRadius: "99px", letterSpacing: "0.04em", flexShrink: 0 },
  eventName: { fontSize: "25px", fontWeight: "800", color: "#fff", lineHeight: 1.6 },
  eventMeta: { fontSize: "18px", color: "rgba(255,255,255,0.7)", marginTop: "2px" },
  chipRow:   { display: "flex", gap: "8px" },
  chip:      { display: "inline-flex", alignItems: "center", gap: "6px", background: "rgba(0,0,0,0.5)", backdropFilter: "blur(6px)", border: "1px solid rgba(255,255,255,0.2)", color: "#fff", fontSize: "18px", fontWeight: "600", padding: "6px 14px", borderRadius: "99px" },
};

// ── Fuel Score Card ───────────────────────────────────────────────────────────
function FuelScoreCard({ fuelScore, consumed, targets, accentColor }) {
  const score = fuelScore?.fuel_score;
  const color = score != null ? scoreColor(score) : "#8aa898";
  const r = 36, circ = 2 * Math.PI * r;
  const fill = score != null ? circ - (score / 100) * circ : circ;

  const bars = [
    { label: "Carbs",     val: Math.round(consumed.carbs_g ?? 0), target: targets.carbs_g ?? targets.carbs_g_max, unit: "g",    color: "#16a34a" },
    { label: "Protein",   val: Math.round(consumed.protein_g),    target: targets.protein_g ?? Math.round((targets.protein_g_min + targets.protein_g_max) / 2), unit: "g", color: "#d97706" },
    { label: "Hydration", val: Math.round(consumed.water_oz),     target: targets.hydration_oz ?? targets.hydration_oz_max, unit: "oz", color: "#0ea5e9" },
  ];

  return (
    <div style={fc.card}>
      {/* Left — score ring */}
      <div style={fc.ringWrap}>
        <div style={{ position: "relative", width: 88, height: 88, flexShrink: 0 }}>
          <svg width="88" height="88" viewBox="0 0 88 88">
            <circle cx="44" cy="44" r={r} fill="none" stroke="#dce8e0" strokeWidth="8" />
            <circle cx="44" cy="44" r={r} fill="none" stroke={color} strokeWidth="8"
              strokeDasharray={circ} strokeDashoffset={fill} strokeLinecap="round"
              transform="rotate(-90 44 44)" style={{ transition: "stroke-dashoffset 0.8s ease" }} />
          </svg>
          <div style={fc.ringInner}>
            {score != null
              ? <><div style={{ ...fc.scoreNum, color }}>{score}</div><div style={fc.scoreOf}>/100</div></>
              : <div style={fc.scoreDash}>—</div>
            }
          </div>
        </div>
        <div style={{ ...fc.scoreLbl, color }}>
          {score != null ? `${scoreEmoji(score)} ${scoreLabel(score)}` : "Log meals"}
        </div>
      </div>

      {/* Right — macro bars */}
      <div style={fc.bars}>
        {bars.map(b => {
          const pct = Math.min(100, b.target > 0 ? Math.round(b.val / b.target * 100) : 0);
          const over = b.val > b.target;
          return (
            <div key={b.label} style={fc.barRow}>
              <div style={fc.barTop}>
                <span style={fc.barLabel}>{b.label}</span>
                <span style={{ ...fc.barVal, color: over ? "#dc2626" : "#1b3a2a" }}>
                  {b.val}<span style={fc.barUnit}>{b.unit}</span>
                </span>
              </div>
              <div style={fc.track}>
                <div style={{ ...fc.fill, width: `${pct}%`, background: over ? "#dc2626" : b.color }} />
              </div>
              <div style={fc.barTarget}>{b.target}{b.unit} target</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
const fc = {
  card:      { background: "#fff", border: "1.5px solid #e5e7eb", borderRadius: "16px", padding: "16px", display: "flex", gap: "16px", alignItems: "flex-start", marginBottom: "20px", boxShadow: "0 2px 12px rgba(0,0,0,0.06)" },
  ringWrap:  { display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, gap: "4px" },
  ringInner: { position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" },
  scoreNum:  { fontSize: "25px", fontWeight: "900", lineHeight: 1 },
  scoreOf:   { fontSize: "15px", color: "#4a6358" },
  scoreDash: { fontSize: "25px", fontWeight: "800", color: "#4a6358" },
  scoreLbl:  { fontSize: "16px", fontWeight: "700", textAlign: "center", marginTop: "2px" },
  bars:      { flex: 1, minWidth: 0 },
  barRow:    { marginBottom: "10px" },
  barTop:    { display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "4px" },
  barLabel:  { fontSize: "16px", fontWeight: "700", color: "#4a6358", textTransform: "uppercase", letterSpacing: "0.04em" },
  barVal:    { fontSize: "19px", fontWeight: "800" },
  barUnit:   { fontSize: "15px", fontWeight: "400", color: "#4a6358", marginLeft: "1px" },
  track:     { height: "5px", background: "#f0f4f1", borderRadius: "99px", overflow: "hidden", marginBottom: "2px" },
  fill:      { height: "100%", borderRadius: "99px", transition: "width 0.6s ease" },
  barTarget: { fontSize: "15px", color: "#4a6358" },
};

// ── Timeline row ──────────────────────────────────────────────────────────────
function TimelineRow({ item, status, accentColor, accentLight, onLog, logging, logged }) {
  if (item.isMarker) return (
    <div style={tr.markerRow}>
      <div style={{ ...tr.markerLine, background: accentColor + "55" }} />
      <div style={{ ...tr.markerBadge, background: accentColor }}>{item.icon} {item.label}</div>
      <div style={{ ...tr.markerLine, background: accentColor + "55" }} />
    </div>
  );

  const isLogged         = logged;
  const isPast           = isLogged;                          // greyed out only if actually logged
  const isPastUnlogged   = status === "past" && !isLogged;    // past time, not yet logged — still actionable
  const isNext           = status === "next" && !isLogged;
  const dotClr = isPast ? "#c8d8d0" : accentColor;
  const photo  = MEAL_PHOTO[item.label];

  return (
    <div style={tr.row}>
      {/* Time column */}
      <div style={tr.timeCol}>
        <div style={{ ...tr.timeText, color: isPast ? "#8aa898" : (isNext || isPastUnlogged) ? accentColor : "#4a6358" }}>
          {fmt(item.time)}
        </div>
      </div>

      {/* Connector */}
      <div style={tr.connector}>
        {isNext
          ? <div style={{ ...tr.dotRing, borderColor: accentColor }}><div style={{ ...tr.dot, background: accentColor }} /></div>
          : <div style={{ ...tr.dot, background: dotClr, margin: "4px 0" }} />
        }
        <div style={{ ...tr.line, background: isPast ? "#f0f4f1" : accentColor + "30" }} />
      </div>

      {/* Content */}
      <div style={{ ...tr.content, opacity: isPast ? 0.42 : 1 }}>
        {isNext ? (
          // ── Highlighted "UP NEXT" card ──
          <div style={{ ...tr.nextCard, borderColor: accentColor, background: accentLight }}>
            <div style={tr.nextTop}>
              <div style={tr.nextLeft}>
                <div style={tr.nextBadge(accentColor)}>UP NEXT</div>
                <div style={tr.nextTitle}>{item.icon} {item.label}</div>
                <div style={tr.nextMealName}>{item.meal}</div>
                {item.kcal && <div style={tr.nextKcal}>{item.kcal} kcal</div>}
              </div>
              {photo && (
                <img
                  src={photo} alt={item.label} loading="lazy"
                  style={{ ...tr.nextPhoto, borderColor: accentColor + "44" }}
                  onError={e => e.target.style.display = "none"}
                />
              )}
            </div>
            {item.tip && (
              <div style={{ ...tr.tip, borderLeftColor: accentColor }}>
                {item.urgent ? "⚠ " : "💡 "}{item.tip}
              </div>
            )}
            <button
              style={{ ...tr.logBtn, background: accentColor, opacity: logging ? 0.6 : 1 }}
              onClick={() => onLog(item)} disabled={logging}
            >
              {logging ? "Logging…" : "I Ate This"}
            </button>
          </div>
        ) : (
          // ── Regular row (logged, past-unlogged, or upcoming) ──
          <div style={tr.normalRow}>
            <div style={tr.normalMain}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "1px" }}>
                <div style={tr.normalLabel}>{item.icon} {item.label}</div>
                {isPast && <span style={tr.fueledPill}>✓ Fueled</span>}
              </div>
              <div style={tr.normalMeal}>{item.meal}{item.kcal ? ` · ${item.kcal} kcal` : ""}</div>
              {isPastUnlogged && (
                <button
                  style={{ ...tr.lateLogBtn, borderColor: accentColor, color: accentColor, opacity: logging ? 0.5 : 1 }}
                  onClick={() => onLog(item)} disabled={logging}
                >
                  {logging ? "Logging…" : "I Ate This"}
                </button>
              )}
              {!isPast && !isPastUnlogged && item.tip && item.urgent && (
                <div style={tr.urgentTip}>⚠ {item.tip}</div>
              )}
            </div>
            {photo && !isPast && (
              <img
                src={photo} alt={item.label} loading="lazy"
                style={tr.thumbPhoto}
                onError={e => e.target.style.display = "none"}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
const tr = {
  row:        { display: "flex", alignItems: "flex-start" },
  timeCol:    { width: "76px", flexShrink: 0, textAlign: "right", paddingRight: "14px", paddingTop: "8px" },
  timeText:   { fontSize: "17px", fontWeight: "700" },
  connector:  { display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: "20px" },
  dot:        { width: "11px", height: "11px", borderRadius: "50%", flexShrink: 0 },
  dotRing:    { width: "19px", height: "19px", borderRadius: "50%", border: "2px solid", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  line:       { width: "2px", flex: 1, minHeight: "24px" },
  content:    { flex: 1, paddingLeft: "12px", paddingBottom: "10px", paddingTop: "4px" },
  // next card
  nextCard:   { border: "2px solid", borderRadius: "14px", padding: "14px", overflow: "hidden" },
  nextTop:    { display: "flex", justifyContent: "space-between", gap: "10px", marginBottom: "10px" },
  nextLeft:   { flex: 1, minWidth: 0 },
  nextBadge:  c => ({ display: "inline-block", background: c, color: "#fff", fontSize: "15px", fontWeight: "800", letterSpacing: "0.08em", padding: "2px 8px", borderRadius: "99px", marginBottom: "6px" }),
  nextTitle:  { fontSize: "20px", fontWeight: "800", color: "#1b3a2a", marginBottom: "2px" },
  nextMealName:{ fontSize: "18px", fontWeight: "600", color: "#4a6358", marginBottom: "2px" },
  nextKcal:   { fontSize: "17px", color: "#4a6358" },
  nextPhoto:  { width: "72px", height: "72px", borderRadius: "12px", objectFit: "cover", flexShrink: 0, border: "2px solid" },
  tip:        { fontSize: "17px", color: "#4a6358", borderLeft: "3px solid", paddingLeft: "8px", lineHeight: 1.5, marginBottom: "10px", background: "rgba(0,0,0,0.03)", padding: "6px 8px", borderRadius: "0 6px 6px 0" },
  logBtn:     { width: "100%", padding: "10px", border: "none", borderRadius: "8px", color: "#fff", fontSize: "19px", fontWeight: "700", cursor: "pointer" },
  // normal row
  normalRow:  { display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px", paddingBottom: "2px" },
  normalMain: { flex: 1, minWidth: 0 },
  normalLabel:{ fontSize: "18px", fontWeight: "700", color: "#4a6358" },
  fueledPill: { fontSize: "13px", fontWeight: "700", color: "#2d6a4f", background: "#e6f4ec", border: "1px solid #b0e8c8", borderRadius: "99px", padding: "2px 8px", flexShrink: 0 },
  normalMeal: { fontSize: "17px", color: "#4a6358" },
  lateLogBtn: { marginTop: "6px", padding: "5px 12px", background: "transparent", border: "1.5px solid", borderRadius: "8px", fontSize: "17px", fontWeight: "700", fontFamily: "'Nunito', sans-serif", cursor: "pointer", display: "inline-block" },
  urgentTip:  { fontSize: "16px", color: "#b45309", marginTop: "2px", fontWeight: "600" },
  thumbPhoto: { width: "40px", height: "40px", borderRadius: "8px", objectFit: "cover", flexShrink: 0, border: "1.5px solid #e5e7eb" },
  // marker
  markerRow:  { display: "flex", alignItems: "center", gap: "8px", margin: "6px 0" },
  markerLine: { flex: 1, height: "1.5px" },
  markerBadge:{ flexShrink: 0, color: "#fff", fontSize: "17px", fontWeight: "800", padding: "4px 14px", borderRadius: "99px" },
};

// ── Fueling guides per day type ───────────────────────────────────────────────
const FUELING_GUIDES = {
  training: {
    title: "Fueling for Training Day",
    color: "#c8903a",
    bg: "#fdf5e7",
    border: "#f4d3a0",
    steps: [
      { time: "Breakfast (7:00–8:00 AM)", body: "Start the day with carbohydrates and protein — eggs and toast, oatmeal, or yogurt and fruit. This refills energy stores after sleep and supports focus, growth, and performance later in the day." },
      { time: "Mid-Morning Snack (10:00–10:30 AM)", body: "Fruit, yogurt, cheese, or a protein smoothie maintains steady energy and prevents long gaps without fuel." },
      { time: "Lunch (12:00–1:00 PM)", body: "A balanced lunch builds the energy foundation your muscles will use during evening practice. Don't skip it." },
      { time: "Pre-Training Meal (4:30–5:00 PM)", body: "Eat carbohydrates and protein 2–3 hours before practice. This is your primary fuel source for training." },
      { time: "Pre-Practice Snack (6:30–7:00 PM)", body: "A light, easy-to-digest snack — banana, granola bar, or applesauce — gives quick energy before stepping onto the field." },
      { time: "After Practice (9:30–10:00 PM)", body: "Recovery snack with protein and carbohydrates within 30 minutes: chocolate milk, Greek yogurt with fruit, or a smoothie. This replenishes energy, repairs muscles, and supports overnight recovery." },
    ],
    reminder: "Great training sessions are fueled throughout the day — not just before practice.",
  },
  practice: {
    title: "Fueling for Practice Day",
    color: "#c8903a",
    bg: "#fdf5e7",
    border: "#f4d3a0",
    steps: [
      { time: "Breakfast (7:00–8:00 AM)", body: "Start the day with carbohydrates and protein — eggs and toast, oatmeal, or yogurt and fruit. This refills energy stores after sleep and supports focus, growth, and performance later in the day." },
      { time: "Mid-Morning Snack (10:00–10:30 AM)", body: "Fruit, yogurt, cheese, or a protein smoothie maintains steady energy and prevents long gaps without fuel." },
      { time: "Lunch (12:00–1:00 PM)", body: "A balanced lunch builds the energy foundation your muscles will use during evening practice. Don't skip it." },
      { time: "Pre-Practice Meal (2–3 hrs before)", body: "Eat carbohydrates and protein 2–3 hours before practice. This is your primary fuel source." },
      { time: "Pre-Practice Snack (30–60 min before)", body: "A light, easy-to-digest snack — banana, granola bar, or applesauce — gives quick energy before stepping onto the field." },
      { time: "After Practice (within 30 min)", body: "Recovery snack with protein and carbohydrates: chocolate milk, Greek yogurt with fruit, or a smoothie. This replenishes energy and starts muscle repair." },
    ],
    reminder: "Great practice sessions are fueled throughout the day — not just right before.",
  },
  game: {
    title: "Fueling for Game Day",
    color: "#c05a4a",
    bg: "#fdf2f0",
    border: "#f4c0b8",
    steps: [
      { time: "The Night Before", body: "High-carb dinner — pasta, rice, or potatoes with protein. Glycogen loading starts 24–48 hours before kickoff. This meal matters more than anything you eat on game day." },
      { time: "Breakfast (3+ hrs before kickoff)", body: "Your last full meal before the game. Carbs + protein, low fat and fiber — familiar foods only. No new foods on game day." },
      { time: "Pre-Game Snack (30–60 min before)", body: "Light, easy-to-digest carbs only — banana, honey toast, or rice cakes. Keep it small. Nothing heavy or new." },
      { time: "Halftime", body: "Orange slices, a banana, or a natural sports drink. Quick carbs to fuel the second half. Don't wait until you feel tired." },
      { time: "Post-Game Recovery (within 30 min)", body: "Chocolate milk + banana is the gold standard — optimal 3:1 carb-to-protein ratio. The 30-minute window is non-negotiable for muscle repair and glycogen replenishment." },
      { time: "Dinner", body: "A full recovery meal with carbs, protein, and vegetables. This rebuilds glycogen stores and repairs muscle overnight." },
    ],
    reminder: "Games are won at the dinner table the night before — not just on match day.",
  },
  tournament: {
    title: "Fueling for Tournament Day",
    color: "#7e6ab5",
    bg: "#f4f1fb",
    border: "#c8bde8",
    steps: [
      { time: "Tournament Breakfast (2–3 hrs before Game 1)", body: "Your biggest carb meal of the day — oatmeal pancakes, eggs, OJ, and a banana. This fuels multiple games, not just the first." },
      { time: "Before Every Game (30–60 min prior)", body: "Banana, honey, or rice cakes. Easy-digest carbs only. Keep it consistent between games — same snack, same timing." },
      { time: "Between Games (immediately after whistl)", body: "Chocolate milk + banana within 15 minutes. Do not wait. The refuel window between tournament games is shorter than a normal recovery window." },
      { time: "60 min before next game", body: "Light top-up snack — crackers and peanut butter or a granola bar. Enough to sustain energy without causing GI discomfort." },
      { time: "Tournament Dinner", body: "High-carb recovery dinner — pasta or rice with protein. This rebuilds glycogen for the next tournament day." },
      { time: "Bedtime Snack", body: "Greek yogurt or cottage cheese — casein protein repairs muscles while you sleep. Non-negotiable on tournament days." },
    ],
    reminder: "Tournament fueling is a full-day operation. Eat before you're hungry, drink before you're thirsty.",
  },
  strength: {
    title: "Fueling for Strength Day",
    color: "#4a8fc4",
    bg: "#eef5fb",
    border: "#b8d8ef",
    steps: [
      { time: "Breakfast (protein-rich start)", body: "Eggs, Greek yogurt, and toast. Strength days demand more protein from the first meal — your muscles need amino acids available all day." },
      { time: "Mid-Morning Snack", body: "Cheese, a hard-boiled egg, or a protein smoothie. Keep protein intake consistent every 3–4 hours." },
      { time: "Pre-Strength Meal (90 min before)", body: "Moderate carbs + protein, lower fat. 90 minutes allows digestion without discomfort. Turkey wrap, rice + chicken, or a grain bowl." },
      { time: "Post-Workout (within 30 min)", body: "20–25g protein + carbs immediately after lifting — Greek yogurt + banana, a protein smoothie, or chocolate milk. This is the single most impactful nutrition moment for strength gains." },
      { time: "Dinner", body: "Highest protein meal of the week — chicken, fish, or legumes with a grain and vegetables. Continue protein synthesis through the evening." },
      { time: "Bedtime Snack", body: "Cottage cheese or Greek yogurt — casein protein releases slowly for 6–8 hours, repairing muscle fibers as you sleep." },
    ],
    reminder: "Strength is built in the gym but made in the kitchen. Protein timing matters as much as the workout.",
  },
  rest: {
    title: "Fueling for Recovery Day",
    color: "#2d6a4f",
    bg: "#f0faf4",
    border: "#b0e8c8",
    steps: [
      { time: "Breakfast", body: "Anti-inflammatory foods — eggs and berries, oatmeal with fruit, or a grain bowl with vegetables. Recovery doesn't stop on rest days; your body is actively repairing from recent training." },
      { time: "Lunch", body: "Keep protein high. Muscle repair continues for 24–48 hours after intense activity, even when you're not training." },
      { time: "Afternoon Snack", body: "Antioxidant-rich foods — almonds and berries, an apple with nut butter, or hummus with vegetables. These help reduce inflammation from training." },
      { time: "Dinner", body: "Focus on iron and calcium today. Rest days are the best time to absorb these key nutrients — iron for oxygen delivery, calcium for bone strength and peak bone mass." },
      { time: "Bedtime Snack (if needed)", body: "Cottage cheese or Greek yogurt — casein protein works overnight even when you're resting, supporting muscle maintenance during recovery." },
    ],
    reminder: "Rest days are not 'off' days for nutrition — they are repair days. Keep fueling well.",
  },
};

function FuelingGuide({ dayType, accentColor }) {
  const [open, setOpen] = useState(false);
  const guide = FUELING_GUIDES[dayType] || FUELING_GUIDES.rest;

  return (
    <div style={{ ...fg.wrap, borderColor: guide.border, background: open ? guide.bg : "#fff" }}>
      <button style={fg.header} onClick={() => setOpen(o => !o)}>
        <div style={fg.headerLeft}>
          <div style={{ ...fg.headerDot, background: guide.color }} />
          <span style={{ ...fg.headerTitle, color: guide.color }}>{guide.title}</span>
        </div>
        <span style={{ ...fg.chevron, color: guide.color, transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>▾</span>
      </button>

      {open && (
        <div style={fg.body}>
          {guide.steps.map((step, i) => (
            <div key={i} style={fg.step}>
              <div style={{ ...fg.stepTime, color: guide.color }}>{step.time}</div>
              <div style={fg.stepBody}>{step.body}</div>
            </div>
          ))}
          <div style={{ ...fg.reminder, borderLeftColor: guide.color }}>
            💡 <strong>Remember:</strong> {guide.reminder}
          </div>
        </div>
      )}
    </div>
  );
}

const fg = {
  wrap:        { border: "1.5px solid", borderRadius: "14px", marginBottom: "20px", overflow: "hidden", transition: "background 0.2s" },
  header:      { width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 16px", background: "none", border: "none", cursor: "pointer", boxSizing: "border-box" },
  headerLeft:  { display: "flex", alignItems: "center", gap: "10px" },
  headerDot:   { width: "8px", height: "8px", borderRadius: "50%", flexShrink: 0 },
  headerTitle: { fontSize: "18px", fontWeight: "800", fontFamily: "'Nunito', sans-serif", letterSpacing: "0.01em" },
  chevron:     { fontSize: "23px", lineHeight: 1, transition: "transform 0.2s", flexShrink: 0 },
  body:        { padding: "4px 16px 16px" },
  step:        { marginBottom: "14px" },
  stepTime:    { fontSize: "17px", fontWeight: "800", fontFamily: "'Nunito', sans-serif", marginBottom: "3px", letterSpacing: "0.01em" },
  stepBody:    { fontSize: "18px", color: "#4a6358", lineHeight: 1.6 },
  reminder:    { borderLeft: "3px solid", paddingLeft: "12px", fontSize: "18px", color: "#4a6358", lineHeight: 1.6, marginTop: "6px", fontStyle: "italic" },
};

// ── Quick action buttons ───────────────────────────────────────────────────────
const ACTIONS = [
  { icon: "🍽️", label: "Log a Meal",   tab: "nutrition",  bg: "#f0faf4", border: "#b0e8c8", ic: "#2d6a4f" },
  { icon: "📅",  label: "Schedule",     tab: "schedule",   bg: "#eef5fb", border: "#b8d8ef", ic: "#4a8fc4" },
  { icon: "🍳",  label: "Meal Planner", tab: "meal-plan",  bg: "#fdf5e7", border: "#f4d3a0", ic: "#c8903a" },
  { icon: "💧",  label: "Hydration",    tab: "hydration",  bg: "#eef5fb", border: "#b8d8ef", ic: "#4a8fc4" },
];

// ── Main ──────────────────────────────────────────────────────────────────────
export default function HomeScreen({ athlete, onNavigate }) {
  const [targets,    setTargets]    = useState(null);
  const [meals,      setMeals]      = useState([]);
  const [todayEvent, setTodayEvent] = useState(null);
  const [fuelScore,  setFuelScore]  = useState(null);
  const [loading,    setLoading]    = useState(true);
  const [loadError,  setLoadError]  = useState(false);
  const [reloadKey,  setReloadKey]  = useState(0);
  const [logging,    setLogging]    = useState(false);

  // Derive logged labels from meals array — single source of truth, always in sync
  const loggedSlots = useMemo(() => new Set(
    meals
      .filter(m => m.log_method === "meal-plan" && m.description?.includes(":"))
      .map(m => m.description.split(":")[0].trim())
  ), [meals]);

  const fetchHome = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const [tRes, mRes, evRes] = await Promise.all([
        fetch(`${API}/api/nutrition/targets/${athlete.id}?date=${TODAY}`),
        fetch(`${API}/api/meals/athlete/${athlete.id}?date=${TODAY}`),
        fetch(`${API}/api/events/athlete/${athlete.id}?date=${TODAY}`),
      ]);
      const t  = tRes.ok  ? await tRes.json()  : null;
      const m  = mRes.ok  ? await mRes.json()  : [];
      const ev = evRes.ok ? await evRes.json() : [];
      setTargets(t); setMeals(m); setTodayEvent(ev[0] || null);
      if (t) {
        const sr = await fetch(`${API}/api/reports/${athlete.id}/daily?date=${TODAY}`);
        if (sr.ok) { const sd = await sr.json(); if (sd.fuel_score !== undefined) setFuelScore(sd); }
      }
    } catch (_) { setLoadError(true); }
    finally { setLoading(false); }
  }, [athlete.id]);

  useEffect(() => { fetchHome(); }, [fetchHome, reloadKey]);

  const consumed = meals.reduce(
    (a, m) => ({ calories: a.calories + (m.calories||0), carbs_g: a.carbs_g + (m.carbs_g||0), protein_g: a.protein_g + (m.protein_g||0), water_oz: a.water_oz + (m.water_oz||0) }),
    { calories: 0, carbs_g: 0, protein_g: 0, water_oz: 0 }
  );

  const dayType  = todayEvent?.event_type || targets?.event_type || "rest";
  const day      = DAY_CFG[dayType] || DAY_CFG.rest;
  const schedule = buildSchedule(dayType, todayEvent?.start_time, todayEvent?.duration_hours);

  const now = Date.now();
  let nextFound = false;
  const statusMap = schedule.map(item => {
    if (item.isMarker) return "marker";
    if (!nextFound && item.time.getTime() > now - 30 * 60_000) { nextFound = true; return "next"; }
    if (!nextFound) return "past";
    return "upcoming";
  });

  async function handleLog(item) {
    if (logging || loggedSlots.has(item.label)) return;
    setLogging(true);
    const mac = MACROS[item.meal] || {};
    try {
      const res = await fetch(`${API}/api/meals/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ athlete_id: athlete.id, log_method: "meal-plan", description: `${item.label}: ${item.meal}`, ...mac, water_oz: 0 }),
      });
      if (!res.ok) throw new Error("Failed to log meal");
      // Optimistic update — include description + log_method so loggedSlots derives correctly
      setMeals(p => [...p, { ...mac, log_method: "meal-plan", description: `${item.label}: ${item.meal}`, water_oz: 0 }]);
      // Re-fetch fuel score so the dial reflects the new nutrition data
      const sr = await fetch(`${API}/api/reports/${athlete.id}/daily?date=${TODAY}`);
      if (sr.ok) { const sd = await sr.json(); if (sd.fuel_score !== undefined) setFuelScore(sd); }
    } catch (_) {}
    finally { setLogging(false); }
  }

  if (loading) return <LoadingState message="Loading today's plan…" />;
  if (loadError) return <ErrorState message="Couldn't load today's plan." onRetry={() => setReloadKey((k) => k + 1)} />;

  return (
    <div style={s.page}>

      {/* ── Photo hero ──────────────────────────────────────────────────────── */}
      <EventHero event={todayEvent} dayType={dayType} athlete={athlete} />

      {/* ── No schedule nudge ───────────────────────────────────────────────── */}
      {!targets && (
        <div style={s.nudge}>
          <span style={{ fontSize: "27px" }}>📅</span>
          <div style={{ flex: 1 }}>
            <div style={s.nudgeHead}>Add your schedule to unlock meal times</div>
            <div style={s.nudgeSub}>AthFuelPath calculates exact windows from your event's kick-off time.</div>
          </div>
          <button style={{ ...s.nudgeBtn, background: day.color }} onClick={() => onNavigate("schedule")}>Add →</button>
        </div>
      )}

      {/* ── Fuel score + macro progress ─────────────────────────────────────── */}
      {targets && (
        <div style={{ position: "relative" }}>
          <FuelScoreCard fuelScore={fuelScore} consumed={consumed} targets={targets} accentColor={day.color} />
          {/* invisible absolute inner for SVG ring overlay */}
        </div>
      )}

      {/* ── Meal timeline ───────────────────────────────────────────────────── */}
      <div style={s.sectionHead}>
        <div style={{ ...s.sectionDot, background: day.grad }} />
        <div style={s.sectionTitle}>Today's Fuel Schedule</div>
      </div>

      <div style={s.timeline}>
        {schedule.map((item, i) => (
          <TimelineRow
            key={i} item={item}
            status={statusMap[i]}
            logged={loggedSlots.has(item.label)}
            accentColor={day.color} accentLight={day.light}
            onLog={handleLog} logging={logging}
          />
        ))}
      </div>

      {/* ── Fueling guide ───────────────────────────────────────────────────── */}
      <FuelingGuide dayType={dayType} accentColor={day.color} />

      {/* ── AI quick fixes ──────────────────────────────────────────────────── */}
      {fuelScore?.gap_fix_suggestions?.length > 0 && (
        <div style={s.fixes}>
          <div style={s.fixesTitle}>💡 Quick fixes for today</div>
          {fuelScore.gap_fix_suggestions.slice(0, 3).map((sg, i) => (
            <div key={i} style={s.fixRow}><div style={{ ...s.fixDot, background: day.color }} />{sg}</div>
          ))}
        </div>
      )}

      <p style={s.disclaimer}>AthFuelPath provides educational food guidance — not medical nutrition therapy.</p>
    </div>
  );
}

const s = {
  page:        { fontFamily: "'Nunito, DM Sans, sans-serif", paddingBottom: "8px" },
  loadingWrap: { display: "flex", flexDirection: "column", alignItems: "center", gap: "14px", padding: "60px 0" },
  spinner:     { width: "30px", height: "30px", border: "3px solid #e5e7eb", borderTopColor: "#2d6a4f", borderRadius: "50%", animation: "spin 0.7s linear infinite" },
  loadingText: { fontSize: "19px", color: "#4a6358" },
  nudge:       { display: "flex", alignItems: "center", gap: "12px", background: "#fffbeb", border: "1.5px solid #fde68a", borderRadius: "12px", padding: "14px 16px", marginBottom: "20px" },
  nudgeHead:   { fontSize: "18px", fontWeight: "700", color: "#92400e", marginBottom: "2px" },
  nudgeSub:    { fontSize: "17px", color: "#92400e", opacity: 0.8 },
  nudgeBtn:    { flexShrink: 0, border: "none", color: "#fff", borderRadius: "8px", padding: "8px 14px", fontSize: "18px", fontWeight: "700", cursor: "pointer" },
  sectionHead: { display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" },
  sectionDot:  { width: "10px", height: "10px", borderRadius: "50%", flexShrink: 0 },
  sectionTitle:{ fontSize: "19px", fontWeight: "700", color: "#1b3a2a" },
  timeline:    { marginBottom: "24px" },
  fixes:       { background: "#fff7ed", border: "1.5px solid #fed7aa", borderRadius: "12px", padding: "14px 16px", marginBottom: "24px" },
  fixesTitle:  { fontSize: "18px", fontWeight: "700", color: "#92400e", marginBottom: "10px" },
  fixRow:      { display: "flex", alignItems: "flex-start", gap: "8px", marginBottom: "6px", fontSize: "18px", color: "#4a6358" },
  fixDot:      { width: "6px", height: "6px", borderRadius: "50%", flexShrink: 0, marginTop: "5px" },
  actionGrid:  { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "24px" },
  actionBtn:   { display: "flex", flexDirection: "column", alignItems: "center", gap: "10px", borderRadius: "14px", padding: "18px 8px", cursor: "pointer" },
  actionIcon:  { width: "44px", height: "44px", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "25px" },
  actionLabel: { fontSize: "18px", fontWeight: "700" },
  disclaimer:  { textAlign: "center", fontSize: "16px", color: "#8aa898", lineHeight: 1.6 },
};
