import { useState, useEffect, useCallback } from "react";
import LoadingState from "./components/LoadingState";
import { LOADING_MESSAGES } from "./constants/loadingMessages";
import { useRotatingMessage } from "./hooks/useRotatingMessage";

const API = import.meta.env.VITE_API_URL ?? "";

const DAY_HERO = {
  rest:       { grad: ["#2d6a4f","#52b788"], emoji:"🌿", badge:"🌿 Rest Day",     title:"Recovery & Rebuild Day",           desc:"No training today — your body is repairing muscle and replenishing glycogen. Focus on protein to rebuild and complex carbs to restore energy stores. Prioritise iron-rich foods and calcium for bone health." },
  practice:   { grad: ["#b45309","#f59e0b"], emoji:"🏃", badge:"🏃 Training Day",  title:"Training Fuel Day",                desc:"Your body needs sustained energy before practice and fast recovery after. Load up on complex carbs at lunch and your pre-training meal, then hit the protein + carb recovery window right after finishing." },
  training:   { grad: ["#b45309","#f59e0b"], emoji:"🏃", badge:"🏃 Training Day",  title:"Training Fuel Day",                desc:"Your body needs sustained energy before practice and fast recovery after. Load up on complex carbs at lunch and your pre-training meal, then hit the protein + carb recovery window right after finishing." },
  strength:   { grad: ["#b45309","#f59e0b"], emoji:"🏋️", badge:"🏋️ Strength Day", title:"Training Fuel Day",                desc:"Your body needs sustained energy before practice and fast recovery after. Load up on complex carbs at lunch and your pre-training meal, then hit the protein + carb recovery window right after finishing." },
  game:       { grad: ["#9a1a1a","#e05a4a"], emoji:"⚽", badge:"⚽ Game Day",       title:"Game Day — Perform & Recover",     desc:"Today is all about peak performance and rapid recovery. Front-load carbs before kick-off, stay on top of hydration throughout, and hit your recovery window within 30 minutes of the final whistle." },
  tournament: { grad: ["#4a2a8a","#9a7ae8"], emoji:"🏆", badge:"🏆 Tournament",   title:"Tournament Day — Fuel to Compete", desc:"Multiple games means fuel management is everything. Prioritise carb availability all day, recover fast between games, and protect your muscles with quality protein at dinner." },
};

const TAG_COLORS = {
  "Complex Carbs":  { bg:"#fff8e7", color:"#b8720a", border:"#f4d3a0" },
  "Quick Carbs":    { bg:"#fff8e7", color:"#b8720a", border:"#f4d3a0" },
  "Fast Carbs":     { bg:"#fff8e7", color:"#b8720a", border:"#f4d3a0" },
  "Protein":        { bg:"#eff8ff", color:"#1a6ab8", border:"#b8d9f4" },
  "High Protein":   { bg:"#eff8ff", color:"#1a6ab8", border:"#b8d9f4" },
  "Light Protein":  { bg:"#eff8ff", color:"#1a6ab8", border:"#b8d9f4" },
  "Casein Protein": { bg:"#f5f0ff", color:"#5a3ab8", border:"#c8b0f4" },
  "Healthy Fats":   { bg:"#fdf5ff", color:"#7a3ab8", border:"#ddbef4" },
  "Light":          { bg:"#f4fdf7", color:"#2a7a4a", border:"#a8e4bc" },
  "Iron-Rich":      { bg:"#fff5e8", color:"#92400e", border:"#f3c67a" },
  "Electrolytes":   { bg:"#e8f4ff", color:"#1a6aa8", border:"#a0cce8" },
  "Fluids":         { bg:"#e8f4ff", color:"#1a6aa8", border:"#a0cce8" },
};

function getMondayOf(d) {
  const day = new Date(d);
  const diff = (day.getDay() + 6) % 7;
  day.setDate(day.getDate() - diff);
  day.setHours(0, 0, 0, 0);
  return day;
}

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function toISO(d) {
  return d.toISOString().split("T")[0];
}

// ── RecipePicker ──────────────────────────────────────────────────────────────
function RecipePicker({ slot, allRecipes, athleteAllergens, onSelect, onClose }) {
  const safeRecipes = allRecipes.filter(r => {
    if (r.category !== slot.recipe_category) return false;
    if (athleteAllergens.some(a => r.allergens.map(x => x.toLowerCase()).includes(a))) return false;
    return true;
  });

  return (
    <div style={rp.panel}>
      <div style={rp.header}>
        <span style={rp.title}>Choose a recipe</span>
        <button style={rp.close} onClick={onClose}>✕</button>
      </div>
      {safeRecipes.length === 0 ? (
        <div style={rp.empty}>No safe recipes found for this slot category.</div>
      ) : (
        <div style={rp.list}>
          {safeRecipes.map(r => (
            <button key={r.id} style={rp.option} onClick={() => onSelect(r)}>
              <div style={rp.optName}>{r.name}</div>
              <div style={rp.optMeta}>
                {r.macros.calories} kcal · {r.macros.carbs_g}g carbs · {r.macros.protein_g}g protein
              </div>
              {r.dietary.length > 0 && (
                <div style={rp.tags}>
                  {r.dietary.slice(0, 3).map(d => <span key={d} style={rp.tag}>{d}</span>)}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
const rp = {
  panel: { background: "#fff", border: "2px solid #0f4c35", borderRadius: "12px", padding: "12px", marginTop: "6px", boxShadow: "0 8px 24px rgba(0,0,0,0.12)", zIndex: 10 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" },
  title: { fontSize: "16px", fontWeight: "700", color: "#2d6a4f" },
  close: { background: "none", border: "none", cursor: "pointer", color: "#4a6358", fontSize: "15px", padding: "2px 6px" },
  empty: { fontSize: "16px", color: "#4a6358", textAlign: "center", padding: "12px 0" },
  list: { display: "flex", flexDirection: "column", gap: "6px", maxHeight: "200px", overflowY: "auto" },
  option: { background: "#f4f8f5", border: "1.5px solid #e5e7eb", borderRadius: "8px", padding: "8px 10px", cursor: "pointer", textAlign: "left" },
  optName: { fontSize: "16px", fontWeight: "700", color: "#1b3a2a", marginBottom: "2px" },
  optMeta: { fontSize: "16px", color: "#4a6358" },
  tags: { display: "flex", gap: "4px", marginTop: "4px", flexWrap: "wrap" },
  tag: { background: "#f0fdf4", color: "#2d6a4f", fontSize: "15px", fontWeight: "600", padding: "1px 6px", borderRadius: "99px" },
};

// ── WeekDots ────────────────────────────────────────────────────────────────
const EVENT_DOT_COLOR = { game:"#c04a3a", tournament:"#7e6ab5", practice:"#c8903a", training:"#c8903a", strength:"#4a8fc4", rest:"#8aa898" };

function WeekDots({ days, selectedDate, onSelect }) {
  return (
    <div style={wd.wrap}>
      {days.map(day => {
        const isActive   = day.date === selectedDate;
        const hasPlanned = day.slots.some(s => s.recipe_id);
        const evColor    = EVENT_DOT_COLOR[day.event_type] || EVENT_DOT_COLOR.rest;
        const d = new Date(day.date + "T12:00:00").getDate();
        return (
          <div key={day.date} style={wd.col} onClick={() => onSelect(day.date)}>
            <div style={{ ...wd.dot, ...(isActive ? wd.dotActive : hasPlanned ? wd.dotPlanned : wd.dotEmpty) }}>
              {day.day_label[0]}
            </div>
            <div style={wd.dateNum}>{d}</div>
            <div style={{ ...wd.evDot, background: evColor }} />
          </div>
        );
      })}
    </div>
  );
}
const wd = {
  wrap:       { display:"flex", justifyContent:"space-between", background:"#fff", padding:"10px 20px 12px", borderBottom:"1px solid #f0f4f1" },
  col:        { display:"flex", flexDirection:"column", alignItems:"center", gap:"3px", cursor:"pointer" },
  dot:        { width:"32px", height:"32px", borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"15px", fontWeight:"800" },
  dotActive:  { background:"#2d6a4f", color:"#fff", boxShadow:"0 2px 8px rgba(45,106,79,0.30)" },
  dotPlanned: { background:"#d4ead8", color:"#2d6a4f" },
  dotEmpty:   { background:"#f0f4f1", color:"#8aa898" },
  dateNum:    { fontSize:"13px", color:"#8aa898", fontWeight:"700" },
  evDot:      { width:"5px", height:"5px", borderRadius:"50%" },
};

// ── DayHero ─────────────────────────────────────────────────────────────────
function DayHero({ day }) {
  const hero = DAY_HERO[day.event_type] || DAY_HERO.rest;
  const pct  = day.calorie_target ? Math.min(100, Math.round((day.planned_calories / day.calorie_target) * 100)) : 0;
  return (
    <div style={{ ...dh.card, background: `linear-gradient(135deg, ${hero.grad[0]}, ${hero.grad[1]})` }}>
      <div style={dh.bgEmoji}>{hero.emoji}</div>
      <div style={dh.badge}>{hero.badge}</div>
      <div style={dh.title}>{hero.title}</div>
      <div style={dh.desc}>{hero.desc}</div>
      {day.double_day && (
        <div style={dh.doubleDayAlert}>⚡ Double Event Day — +15% calorie target today</div>
      )}
      <div style={dh.calRow}>
        <div style={dh.calBarWrap}>
          <div style={dh.calTrack}>
            <div style={{ ...dh.calFill, width: `${pct}%` }} />
          </div>
        </div>
        <div style={dh.calLabel}>{day.planned_calories} / {day.calorie_target ?? "–"} kcal</div>
      </div>
    </div>
  );
}
const dh = {
  card:           { margin:"14px 16px 0", borderRadius:"18px", padding:"18px 18px 16px", position:"relative", overflow:"hidden" },
  bgEmoji:        { position:"absolute", right:"-10px", top:"-10px", fontSize:"93px", opacity:"0.12", transform:"rotate(10deg)", userSelect:"none", lineHeight:1 },
  badge:          { display:"inline-flex", alignItems:"center", gap:"5px", background:"rgba(255,255,255,0.22)", border:"1px solid rgba(255,255,255,0.30)", padding:"3px 10px", borderRadius:"20px", fontSize:"15px", fontWeight:"700", color:"#fff", marginBottom:"8px" },
  title:          { fontSize:"17px", fontWeight:"900", color:"#fff", marginBottom:"6px", lineHeight:"1.2", fontFamily:"'Nunito', sans-serif" },
  desc:           { fontSize:"16px", color:"rgba(255,255,255,0.88)", lineHeight:"1.6" },
  doubleDayAlert: { marginTop:"8px", background:"rgba(255,255,255,0.20)", borderRadius:"8px", padding:"5px 10px", fontSize:"15px", fontWeight:"700", color:"#fff" },
  calRow:         { marginTop:"12px", background:"rgba(255,255,255,0.18)", borderRadius:"10px", padding:"8px 12px", display:"flex", alignItems:"center", gap:"10px" },
  calBarWrap:     { flex:1 },
  calTrack:       { height:"5px", background:"rgba(255,255,255,0.25)", borderRadius:"99px", overflow:"hidden" },
  calFill:        { height:"100%", background:"rgba(255,255,255,0.80)", borderRadius:"99px", transition:"width 0.4s ease" },
  calLabel:       { fontSize:"15px", color:"rgba(255,255,255,0.90)", fontWeight:"700", whiteSpace:"nowrap" },
};

// ── TimelineSlot ──────────────────────────────────────────────────────────────
function TimelineSlot({ slot, date, allRecipes, athleteAllergens, isActive, isLast,
                        onOpenPicker, onClosePicker, onAssign, onAutoSwap, onClear }) {
  if (slot.double_day_alert) {
    return (
      <div style={ts.alertBanner}>
        <span style={ts.alertIcon}>⚡</span>
        <div>
          <div style={ts.alertTitle}>Double Event Day</div>
          <div style={ts.alertSub}>Two events today — calorie targets increased by 15%</div>
        </div>
      </div>
    );
  }

  const filled = !!slot.recipe_id;

  return (
    <div style={ts.wrap}>
      <div style={ts.lineCol}>
        <div style={{ ...ts.dot, ...(slot.is_hydration ? ts.dotHydration : filled ? ts.dotFilled : ts.dotEmpty) }} />
        {!isLast && <div style={ts.line} />}
      </div>
      <div style={ts.cardCol}>
        <div style={ts.cardHeader}>
          <div style={{ ...ts.iconWrap, ...(slot.is_hydration ? ts.iconWrapBlue : ts.iconWrapGreen) }}>
            {slot.icon}
          </div>
          <div style={ts.headerText}>
            <div style={ts.slotName}>{slot.display_label}</div>
            <div style={ts.eatBy}>
              {slot.is_hydration ? "💧" : "⏰"} {slot.eat_by_time}
              {slot.note ? <span style={ts.conflictNote}> · {slot.note}</span> : null}
            </div>
          </div>
        </div>

        {slot.tags.length > 0 && (
          <div style={ts.tags}>
            {slot.tags.map(tag => {
              const c = TAG_COLORS[tag] || { bg:"#f0f4f1", color:"#4a6358", border:"#dce8e0" };
              return <span key={tag} style={{ ...ts.tag, background:c.bg, color:c.color, borderColor:c.border }}>{tag}</span>;
            })}
          </div>
        )}

        {slot.is_hydration ? (
          <div style={ts.hydrationInfo}>Water target based on today&apos;s training load</div>
        ) : filled ? (
          <div style={{ ...ts.filledCard, ...(slot.is_merged ? ts.mergedCard : {}), ...(slot.is_ai_generated ? ts.aiCard : {}) }}>
            {slot.is_ai_generated && <div style={ts.aiBadge}>✨ AI</div>}
            <div style={ts.recipeName}>{slot.recipe_name}</div>
            <div style={ts.recipeCal}>{slot.calories} kcal</div>
            <div style={ts.actions}>
              <button style={ts.btnSwap} onClick={() => onAutoSwap(date, slot.slot_name)}>🔄 Swap</button>
              <button style={ts.btnClear} onClick={() => onClear(date, slot.slot_name)}>✕ Remove</button>
            </div>
          </div>
        ) : (
          <button style={ts.addBtn} onClick={() => onOpenPicker(date, slot.slot_name)}>
            ＋ {slot.is_merged ? "Add Recovery Dinner" : "Add Meal"}
          </button>
        )}

        {isActive && (
          <RecipePicker
            slot={slot}
            allRecipes={allRecipes}
            athleteAllergens={athleteAllergens}
            onSelect={recipe => { onAssign(date, slot.slot_name, recipe); onClosePicker(); }}
            onClose={onClosePicker}
          />
        )}
      </div>
    </div>
  );
}
const ts = {
  wrap:         { display:"flex", gap:"0", marginBottom:"0" },
  lineCol:      { display:"flex", flexDirection:"column", alignItems:"center", width:"24px", flexShrink:0, paddingTop:"8px" },
  dot:          { width:"12px", height:"12px", borderRadius:"50%", flexShrink:0, zIndex:1 },
  dotFilled:    { background:"#2d6a4f", border:"2px solid #2d6a4f" },
  dotEmpty:     { background:"#fff", border:"2px solid #2d6a4f" },
  dotHydration: { background:"#1a6ab8", border:"2px solid #1a6ab8" },
  line:         { width:"2px", flex:1, background:"linear-gradient(to bottom, #2d6a4f, #b0e8c8)", marginTop:"3px" },
  cardCol:      { flex:1, paddingBottom:"14px" },
  cardHeader:   { display:"flex", alignItems:"flex-start", gap:"10px", marginBottom:"8px" },
  iconWrap:     { width:"38px", height:"38px", borderRadius:"11px", display:"flex", alignItems:"center", justifyContent:"center", fontSize:"22px", flexShrink:0 },
  iconWrapGreen:{ background:"#f0fdf4" },
  iconWrapBlue: { background:"#e8f4ff" },
  headerText:   { flex:1 },
  slotName:     { fontSize:"15px", fontWeight:"800", color:"#1b3a2a", lineHeight:"1.2", fontFamily:"'Nunito', sans-serif" },
  eatBy:        { fontSize:"15px", color:"#2d6a4f", fontWeight:"700", marginTop:"2px" },
  conflictNote: { color:"#b45309", fontWeight:"600" },
  tags:         { display:"flex", flexWrap:"wrap", gap:"5px", marginBottom:"10px" },
  tag:          { padding:"3px 9px", borderRadius:"20px", fontSize:"14px", fontWeight:"700", border:"1.5px solid" },
  hydrationInfo:{ fontSize:"15px", color:"#5a8ab8", fontStyle:"italic", padding:"6px 0" },
  filledCard:   { background:"#f4f8f5", border:"1.5px solid #e5e7eb", borderRadius:"10px", padding:"10px 12px" },
  mergedCard:   { background:"#f5f0ff", borderColor:"#dbbef4" },
  aiCard:       { background:"#f0fdf4", borderColor:"#b0e8c8" },
  aiBadge:      { fontSize:"13px", fontWeight:"800", color:"#2d6a4f", marginBottom:"2px" },
  recipeName:   { fontSize:"14px", fontWeight:"700", color:"#1b3a2a", marginBottom:"2px", lineHeight:"1.4" },
  recipeCal:    { fontSize:"16px", color:"#4a6358", marginBottom:"8px" },
  actions:      { display:"flex", gap:"6px" },
  btnSwap:      { background:"#f0f4f1", border:"none", borderRadius:"7px", padding:"6px 10px", fontSize:"16px", cursor:"pointer", color:"#4a6358", fontWeight:"600" },
  btnClear:     { background:"#fef2f2", border:"none", borderRadius:"7px", padding:"6px 10px", fontSize:"16px", cursor:"pointer", color:"#dc2626", fontWeight:"600" },
  addBtn:       { width:"100%", padding:"9px 12px", background:"#f0fdf4", border:"1.5px solid #2d6a4f", borderRadius:"9px", color:"#2d6a4f", fontSize:"14px", fontWeight:"700", cursor:"pointer" },
  alertBanner:  { display:"flex", alignItems:"center", gap:"10px", background:"#fffbeb", border:"1.5px solid #fde68a", borderRadius:"12px", padding:"10px 14px", marginBottom:"14px" },
  alertIcon:    { fontSize:"23px" },
  alertTitle:   { fontSize:"14px", fontWeight:"800", color:"#92400e" },
  alertSub:     { fontSize:"15px", color:"#b45309" },
};

// ── MealPlannerScreen ─────────────────────────────────────────────────────────
export default function MealPlannerScreen({ athlete, onNavigate, freshImport = false, onFreshImportSeen }) {
  const todayISO = new Date().toISOString().split("T")[0];
  const [weekStart, setWeekStart]       = useState(getMondayOf(new Date()));
  const [selectedDate, setSelectedDate] = useState(todayISO);
  const [weekData, setWeekData]         = useState(null);
  const [allRecipes, setAllRecipes]     = useState([]);
  const [activeSlot, setActiveSlot]     = useState(null);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");

  const athleteAllergens = (athlete.allergies || "").split(",").map(a => a.trim().toLowerCase()).filter(Boolean);

  const planMsg = useRotatingMessage(LOADING_MESSAGES.meal_plan_gen, { active: loading });

  useEffect(() => {
    fetch(`${API}/api/recipes/`)
      .then(r => r.json())
      .then(data => setAllRecipes(data.recipes || []))
      .catch(() => {});
  }, []);

  const loadWeek = useCallback(async () => {
    setLoading(true); setError("");
    const res = await fetch(`${API}/api/meal-plans/${athlete.id}?week_start=${toISO(weekStart)}`);
    if (res.ok) setWeekData(await res.json());
    else setError("Failed to load meal plan.");
    setLoading(false);
  }, [athlete.id, weekStart]);

  useEffect(() => { loadWeek(); }, [loadWeek]);

  function goToPrevDay() {
    const prev = addDays(new Date(selectedDate + "T12:00:00"), -1);
    const monday = getMondayOf(prev);
    if (toISO(monday) !== toISO(weekStart)) setWeekStart(monday);
    setSelectedDate(toISO(prev));
    setActiveSlot(null);
  }

  function goToNextDay() {
    const next = addDays(new Date(selectedDate + "T12:00:00"), 1);
    const monday = getMondayOf(next);
    if (toISO(monday) !== toISO(weekStart)) setWeekStart(monday);
    setSelectedDate(toISO(next));
    setActiveSlot(null);
  }

  async function handleAssign(date, slotName, recipe) {
    const res = await fetch(`${API}/api/meal-plans/${athlete.id}/slot`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_date: date, slot_name: slotName, recipe_id: recipe.id }),
    });
    if (res.ok) {
      const updated = await res.json();
      updateSlotInState(date, slotName, updated);
    }
  }

  function handleAutoSwap(date, slotName) {
    const day = weekData?.days.find(d => d.date === date);
    const slot = day?.slots.find(s => s.slot_name === slotName);
    if (!slot?.recipe_category) return;
    const safe = allRecipes.filter(r =>
      r.category === slot.recipe_category &&
      !athleteAllergens.some(a => r.allergens.map(x => x.toLowerCase()).includes(a))
    );
    const alts = safe.filter(r => r.id !== slot.recipe_id);
    if (!alts.length) return;
    handleAssign(date, slotName, alts[Math.floor(Math.random() * alts.length)]);
  }

  async function handleClear(date, slotName) {
    const res = await fetch(`${API}/api/meal-plans/${athlete.id}/slot?plan_date=${date}&slot_name=${slotName}`, { method: "DELETE" });
    if (res.ok) updateSlotInState(date, slotName, { recipe_id: null, recipe_name: null, calories: null, carbs_g: null, protein_g: null, fat_g: null, is_ai_generated: false, logged: false });
  }

  function updateSlotInState(date, slotName, patch) {
    setWeekData(prev => {
      if (!prev) return prev;
      const days = prev.days.map(day => {
        if (day.date !== date) return day;
        const slots = day.slots.map(s => s.slot_name === slotName ? { ...s, ...patch } : s);
        const planned = slots.reduce((sum, s) => sum + (s.calories || 0), 0);
        return { ...day, slots, planned_calories: Math.round(planned) };
      });
      return { ...prev, days };
    });
  }

  const selectedDay = weekData?.days.find(d => d.date === selectedDate) ?? null;
  const selectedDt  = new Date(selectedDate + "T12:00:00");

  return (
    <div>
      {freshImport && (
        <div style={s.importBanner}>
          <div style={s.importBannerInner}>
            <div style={s.importBannerText}>
              <div style={s.importBannerTitle}>🎉 Schedule loaded — meal slots are ready!</div>
              <div style={s.importBannerSub}>Tap each day to plan meals for that day.</div>
            </div>
            <button style={s.importBannerClose} onClick={onFreshImportSeen}>✕</button>
          </div>
        </div>
      )}

      <div style={s.headerRow}>
        <div>
          <h2 style={s.title}>🍳 Meal Planner</h2>
          <p style={s.subtitle}>{athlete.first_name}&apos;s daily fueling plan</p>
        </div>
        <div style={s.toggleWrap}>
          <div style={s.toggleActive}>Day</div>
          <div style={s.toggleDisabled} title="Coming soon">Week</div>
        </div>
      </div>

      {error && <div style={s.errorBox}>{error}</div>}

      {loading ? (
        <LoadingState message={planMsg} />
      ) : weekData ? (
        <>
          <WeekDots
            days={weekData.days}
            selectedDate={selectedDate}
            onSelect={date => { setSelectedDate(date); setActiveSlot(null); }}
          />

          <div style={s.dayNav}>
            <button style={s.dayNavBtn} onClick={goToPrevDay}>‹</button>
            <div style={s.dayNavCenter}>
              <div style={s.dayNavDow}>
                {selectedDt.toLocaleDateString("en-US", { weekday:"long" }).toUpperCase()}
              </div>
              <div style={s.dayNavDate}>{selectedDt.getDate()}</div>
              <div style={s.dayNavMonth}>
                {selectedDt.toLocaleDateString("en-US", { month:"long", year:"numeric" })}
              </div>
            </div>
            <button style={s.dayNavBtn} onClick={goToNextDay}>›</button>
          </div>

          {selectedDay ? (
            <>
              <DayHero day={selectedDay} />
              <div style={s.timeline}>
                {selectedDay.slots.map((slot, idx) => (
                  <TimelineSlot
                    key={slot.slot_name}
                    slot={slot}
                    date={selectedDay.date}
                    allRecipes={allRecipes}
                    athleteAllergens={athleteAllergens}
                    isActive={activeSlot?.date === selectedDay.date && activeSlot?.slot === slot.slot_name}
                    isLast={idx === selectedDay.slots.length - 1}
                    onOpenPicker={(date, slotName) => setActiveSlot({ date, slot: slotName })}
                    onClosePicker={() => setActiveSlot(null)}
                    onAssign={handleAssign}
                    onAutoSwap={handleAutoSwap}
                    onClear={handleClear}
                  />
                ))}
              </div>
            </>
          ) : (
            <div style={s.loadingMsg}>Select a day above.</div>
          )}
        </>
      ) : null}

      <p style={s.disclaimer}>
        Meal plans are suggestions based on event type and nutrition targets.
        AthFuelPath provides educational food guidance — not medical nutrition therapy.
      </p>
    </div>
  );
}

const s = {
  importBanner:      { margin:"0 0 16px", borderRadius:"14px", background:"linear-gradient(135deg, #0f4c35, #1a7a54)", padding:"1px" },
  importBannerInner: { display:"flex", alignItems:"center", justifyContent:"space-between", gap:"12px", background:"linear-gradient(135deg, #0f4c35, #1a7a54)", borderRadius:"13px", padding:"16px 18px" },
  importBannerText:  { flex:1 },
  importBannerTitle: { fontSize:"16px", fontWeight:"700", color:"#fff", marginBottom:"3px" },
  importBannerSub:   { fontSize:"15px", color:"#b7e4c7", lineHeight:"1.6" },
  importBannerClose: { background:"rgba(255,255,255,0.15)", border:"none", color:"#fff", borderRadius:"50%", width:"28px", height:"28px", cursor:"pointer", fontSize:"15px", flexShrink:0 },

  headerRow:     { display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:"0" },
  title:         { fontSize:"23px", fontWeight:"700", color:"#1b3a2a", margin:"0 0 2px" },
  subtitle:      { fontSize:"14px", color:"#4a6358", margin:"0 0 12px" },

  toggleWrap:    { display:"flex", background:"#f0f4f1", borderRadius:"10px", padding:"3px", gap:"2px", flexShrink:0 },
  toggleActive:  { padding:"5px 14px", borderRadius:"7px", background:"#2d6a4f", color:"#fff", fontSize:"16px", fontWeight:"700", boxShadow:"0 1px 4px rgba(45,106,79,0.25)" },
  toggleDisabled:{ padding:"5px 14px", borderRadius:"7px", color:"#c0c0c0", fontSize:"16px", fontWeight:"700", cursor:"not-allowed" },

  errorBox:      { background:"#fef2f2", border:"1.5px solid #fecaca", borderRadius:"8px", padding:"10px 14px", fontSize:"15px", color:"#dc2626", marginBottom:"12px" },
  loadingMsg:    { textAlign:"center", color:"#4a6358", padding:"40px 0", fontSize:"16px" },

  dayNav:        { display:"flex", alignItems:"center", justifyContent:"space-between", padding:"14px 20px 0" },
  dayNavBtn:     { width:"38px", height:"38px", background:"#fff", border:"1.5px solid #dce8e0", borderRadius:"10px", fontSize:"23px", fontWeight:"700", color:"#4a6358", cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center" },
  dayNavCenter:  { textAlign:"center" },
  dayNavDow:     { fontSize:"15px", color:"#8aa898", fontWeight:"700", letterSpacing:"0.08em" },
  dayNavDate:    { fontSize:"31px", fontWeight:"900", color:"#1b3a2a", lineHeight:"1.1", fontFamily:"'Nunito', sans-serif" },
  dayNavMonth:   { fontSize:"16px", color:"#6b8f7e", marginTop:"1px" },

  timeline:      { padding:"16px 16px 8px", display:"flex", flexDirection:"column" },

  disclaimer:    { fontSize:"16px", color:"#8aa898", textAlign:"center", marginTop:"16px", lineHeight:"1.6", padding:"0 8px 16px" },
};
