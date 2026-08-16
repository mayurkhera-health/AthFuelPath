# Fuel Report Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the NutritionDashboard with a celebration-first Fuel Report tab showing weekly wins, a 6×7 heatmap, and an AI-generated parent report.

**Architecture:** New `nutrition_analysis.py` service computes all weekly math (heatmap pcts, traffic lights, gap ranking, wins). The existing `weekly-summary` endpoint is extended with `week_start` param and new fields. A new `nutrition/` components directory holds 4 focused components assembled by the rewritten `NutritionDashboard.jsx`.

**Tech Stack:** FastAPI + SQLite (Python), React 18 + Vite (no router), inline styles with design tokens matching rest of app.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `api/services/nutrition_analysis.py` | All weekly math: heatmap, traffic light, gaps, wins |
| Modify | `api/routes/today.py:101-157` | Extend weekly-summary with week_start + new payload fields |
| Modify | `api/routes/reports.py:64-106` | Add week_start param, return letter_grade |
| Create | `frontend/src/components/nutrition/WeekNav.jsx` | Sticky week navigation strip |
| Create | `frontend/src/components/nutrition/WinHero.jsx` | Zone 1: celebration banner + wins + focus strip |
| Create | `frontend/src/components/nutrition/WeeklyHeatmap.jsx` | Zone 2: 6-nutrient × 7-day grid |
| Create | `frontend/src/components/nutrition/ParentReport.jsx` | Zone 3: AI weekly report card |
| Rewrite | `frontend/src/NutritionDashboard.jsx` | Page shell — fetches data, renders zones |

---

## Task 1: nutrition_analysis.py

**Files:**
- Create: `api/services/nutrition_analysis.py`

- [ ] **Step 1: Write the file**

```python
from datetime import date as dt_date, timedelta
from api.services.today_service import compute_traffic_light, compute_logged_totals, get_athlete_streak

NUTRIENT_LABELS = {
    "calories":   ("🔥", "Calories"),
    "carbs_g":    ("⚡", "Carbs"),
    "protein_g":  ("💪", "Protein"),
    "iron_mg":    ("🩸", "Iron"),
    "calcium_mg": ("🦴", "Calcium"),
    "water_oz":   ("💧", "Hydration"),
}

WIN_COLORS = {
    "calories": "gold", "carbs_g": "green", "protein_g": "gold",
    "iron_mg": "red", "calcium_mg": "blue", "water_oz": "blue",
}


def get_week_start(reference_date: str = None) -> str:
    d = dt_date.fromisoformat(reference_date) if reference_date else dt_date.today()
    return (d - timedelta(days=d.weekday())).isoformat()


def get_week_dates(week_start: str) -> list:
    start = dt_date.fromisoformat(week_start)
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


def compute_trend(pcts: list) -> str:
    if len(pcts) < 4:
        return "stable"
    mid = len(pcts) // 2
    first = sum(pcts[:mid]) / mid
    second = sum(pcts[mid:]) / (len(pcts) - mid)
    diff = second - first
    if diff > 8: return "improving"
    if diff < -8: return "declining"
    return "stable"


def _get_day_logged(athlete_id: int, date_str: str, conn):
    targets_row = conn.execute(
        "SELECT * FROM daily_targets WHERE athlete_id = ? AND target_date = ?",
        (athlete_id, date_str),
    ).fetchone()
    meal_rows = conn.execute(
        "SELECT * FROM meal_logs WHERE athlete_id = ? AND DATE(logged_at) = ?",
        (athlete_id, date_str),
    ).fetchall()
    if not targets_row or not meal_rows:
        return None, None
    logged = compute_logged_totals([dict(m) for m in meal_rows])
    water_row = conn.execute(
        "SELECT cups FROM water_logs WHERE athlete_id = ? AND log_date = ?",
        (athlete_id, date_str),
    ).fetchone()
    if water_row:
        logged["water_oz"] = round((logged.get("water_oz") or 0) + water_row["cups"] * 8, 1)
    return dict(targets_row), logged


def build_heatmap(athlete_id: int, week_dates: list, conn) -> dict:
    nutrients = ["iron_mg", "calcium_mg", "carbs_g", "protein_g", "calories", "water_oz"]
    heatmap = {n: [] for n in nutrients}
    for date_str in week_dates:
        targets, logged = _get_day_logged(athlete_id, date_str, conn)
        if targets is None:
            for n in nutrients:
                heatmap[n].append(None)
            continue
        tl = compute_traffic_light(targets, logged)
        for n in nutrients:
            heatmap[n].append(tl[n]["pct_met"] if n in tl else None)
    return heatmap


def calculate_weekly_traffic_light(athlete_id: int, week_dates: list, conn) -> dict:
    nutrients = ["iron_mg", "calcium_mg", "carbs_g", "protein_g", "calories", "water_oz"]
    accum = {n: {"pcts": [], "amounts": [], "target": 0} for n in nutrients}
    for date_str in week_dates:
        targets, logged = _get_day_logged(athlete_id, date_str, conn)
        if targets is None:
            continue
        tl = compute_traffic_light(targets, logged)
        for n in nutrients:
            if n in tl:
                accum[n]["pcts"].append(tl[n]["pct_met"])
                accum[n]["amounts"].append(tl[n]["logged"])
                accum[n]["target"] = tl[n]["target"]
    result = {}
    for n in nutrients:
        pcts = accum[n]["pcts"]
        amounts = accum[n]["amounts"]
        if pcts:
            result[n] = {
                "weekly_avg_pct": round(sum(pcts) / len(pcts)),
                "weekly_avg_amount": round(sum(amounts) / len(amounts), 1),
                "target": accum[n]["target"],
                "days_below_target": sum(1 for p in pcts if p < 80),
                "days_logged": len(pcts),
                "trend": compute_trend(pcts),
            }
        else:
            result[n] = {
                "weekly_avg_pct": 0, "weekly_avg_amount": 0,
                "target": accum[n]["target"],
                "days_below_target": 0, "days_logged": 0, "trend": "no_data",
            }
    return result


def rank_weekly_gaps(weekly_tl: dict, gender: str) -> list:
    gaps = [
        {
            "nutrient": n, "avg_pct": d["weekly_avg_pct"],
            "avg_amount": d["weekly_avg_amount"], "target": d["target"],
            "days_below": d["days_below_target"], "days_logged": d["days_logged"],
        }
        for n, d in weekly_tl.items() if d["days_logged"] > 0
    ]
    gaps.sort(key=lambda g: g["avg_pct"])
    if gender.lower() in ("girl", "female", "f"):
        iron = next((g for g in gaps if g["nutrient"] == "iron_mg"), None)
        if iron and iron["avg_pct"] < 75:
            gaps.remove(iron)
            gaps.insert(0, iron)
    return gaps


def build_wins_list(weekly_tl: dict, streak: dict, athlete_name: str) -> list:
    wins = []
    for n, d in weekly_tl.items():
        if len(wins) >= 2:
            break
        if d["days_logged"] >= 2 and d["weekly_avg_pct"] >= 90:
            icon, label = NUTRIENT_LABELS.get(n, ("✓", n))
            wins.append({
                "icon": icon, "color": WIN_COLORS.get(n, "green"),
                "label": f"{label} nailed — every logged day",
                "detail": f"Hit {d['weekly_avg_pct']}% of target on average. Great consistency.",
            })
    if len(wins) < 3:
        for n, d in weekly_tl.items():
            if d["trend"] == "improving" and d["days_logged"] >= 3:
                _, label = NUTRIENT_LABELS.get(n, ("📈", n))
                wins.append({
                    "icon": "📈", "color": "blue",
                    "label": f"{label} trending up all week",
                    "detail": f"At {d['weekly_avg_pct']}% and improving — keep it going.",
                })
                break
    current_streak = streak.get("current_streak", 0)
    best_streak = streak.get("best_streak", 0)
    if current_streak >= 2 and len(wins) < 4:
        is_best = current_streak >= best_streak
        wins.append({
            "icon": "🗓", "color": "purple",
            "label": f"{'Best ever — ' if is_best else ''}{current_streak}-day logging streak",
            "detail": f"Consistency is the hardest part. {athlete_name} is building a real habit.",
        })
    if not wins:
        days = max((d["days_logged"] for d in weekly_tl.values()), default=0)
        wins.append({
            "icon": "📋", "color": "blue",
            "label": f"Showing up — {days} day{'s' if days != 1 else ''} logged this week",
            "detail": f"Every meal logged helps {athlete_name} fuel smarter. Keep going.",
        })
    return wins[:4]
```

- [ ] **Step 2: Verify import works**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && python -c "from api.services.nutrition_analysis import get_week_start, get_week_dates, build_wins_list; print(get_week_dates(get_week_start()))"
```

Expected: `['2026-06-08', '2026-06-09', ..., '2026-06-14']` (current week dates)

- [ ] **Step 3: Commit**

```bash
git add api/services/nutrition_analysis.py
git commit -m "feat(nutrition): add weekly analysis service (heatmap, traffic light, wins)"
```

---

## Task 2: Extend weekly-summary endpoint

**Files:**
- Modify: `api/routes/today.py:101-157`

- [ ] **Step 1: Replace the entire endpoint function**

Replace lines 101–157 (`@router.get("/{athlete_id}/weekly-summary")` through the closing `finally` block) with:

```python
@router.get("/{athlete_id}/weekly-summary")
def get_weekly_summary(athlete_id: int, week_start: str = None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)
        gender = athlete.get("gender", "boy")

        from api.services.nutrition_analysis import (
            get_week_start, get_week_dates, build_heatmap,
            calculate_weekly_traffic_light, rank_weekly_gaps, build_wins_list,
        )
        from api.services.today_service import calc_letter_grade

        resolved_week_start = week_start or get_week_start()
        week_dates = get_week_dates(resolved_week_start)
        today_str = str(dt_date.today())
        DAY_ABBR = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

        week = []
        for i, date_str in enumerate(week_dates):
            targets_row = conn.execute(
                "SELECT * FROM daily_targets WHERE athlete_id = ? AND target_date = ?",
                (athlete_id, date_str),
            ).fetchone()
            event_row = conn.execute(
                "SELECT event_type FROM events WHERE athlete_id = ? AND event_date = ? LIMIT 1",
                (athlete_id, date_str),
            ).fetchone()
            meal_rows = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = ? AND DATE(logged_at) = ?",
                (athlete_id, date_str),
            ).fetchall()
            score = None
            if targets_row and meal_rows:
                water_row = conn.execute(
                    "SELECT cups FROM water_logs WHERE athlete_id = ? AND log_date = ?",
                    (athlete_id, date_str),
                ).fetchone()
                water_cups = water_row["cups"] if water_row else 0
                logged = compute_logged_totals([dict(m) for m in meal_rows])
                logged["water_oz"] = round((logged.get("water_oz") or 0) + water_cups * 8, 1)
                tl = compute_traffic_light(dict(targets_row), logged)
                score = tl["daily_fuel_score"]
            week.append({
                "date": date_str,
                "day_abbr": DAY_ABBR[i],
                "day_num": dt_date.fromisoformat(date_str).day,
                "score": score,
                "event_type": event_row["event_type"] if event_row else None,
                "is_today": date_str == today_str,
            })

        scores = [d["score"] for d in week if d["score"] is not None]
        week_fuel_score = round(sum(scores) / len(scores)) if scores else 0
        days_logged = len(scores)

        heatmap = build_heatmap(athlete_id, week_dates, conn)
        weekly_tl = calculate_weekly_traffic_light(athlete_id, week_dates, conn)
        ranked_gaps = rank_weekly_gaps(weekly_tl, gender)
        streak = get_athlete_streak(athlete_id, conn)
        wins = build_wins_list(weekly_tl, streak, athlete["first_name"])

        prev_start_date = dt_date.fromisoformat(resolved_week_start) - timedelta(days=7)
        prev_dates = [(prev_start_date + timedelta(days=i)).isoformat() for i in range(7)]
        prev_scores = []
        for date_str in prev_dates:
            targets_row = conn.execute(
                "SELECT * FROM daily_targets WHERE athlete_id = ? AND target_date = ?",
                (athlete_id, date_str),
            ).fetchone()
            meal_rows = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = ? AND DATE(logged_at) = ?",
                (athlete_id, date_str),
            ).fetchall()
            if targets_row and meal_rows:
                logged = compute_logged_totals([dict(m) for m in meal_rows])
                tl = compute_traffic_light(dict(targets_row), logged)
                prev_scores.append(tl["daily_fuel_score"])
        prev_week_score = round(sum(prev_scores) / len(prev_scores)) if prev_scores else None

        return {
            "week_start": resolved_week_start,
            "week_end": week_dates[-1],
            "days_logged": days_logged,
            "week_fuel_score": week_fuel_score,
            "prev_week_score": prev_week_score,
            "days": week,
            "heatmap": heatmap,
            "weekly_traffic_light": weekly_tl,
            "ranked_gaps": ranked_gaps,
            "wins": wins,
            "streak": streak,
            "letter_grade": calc_letter_grade(week_fuel_score),
        }
    finally:
        conn.close()
```

- [ ] **Step 2: Verify endpoint starts**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && python -c "from api.routes.today import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add api/routes/today.py
git commit -m "feat(api): extend weekly-summary with week_start, heatmap, wins, gaps"
```

---

## Task 3: Extend weekly reports endpoint

**Files:**
- Modify: `api/routes/reports.py:64-106`

- [ ] **Step 1: Replace `weekly_parent_report` function**

Replace lines 64–106 with:

```python
@router.get("/{athlete_id}/weekly")
def weekly_parent_report(athlete_id: int, week_start: str = None):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM athletes WHERE id = ?", (athlete_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Athlete not found.")
        athlete = dict(row)

        from api.services.nutrition_analysis import get_week_start, get_week_dates
        from api.services.today_service import calc_letter_grade
        from api.services.nutrition_calc import calc_daily_targets

        resolved_week_start = week_start or get_week_start()
        week_dates = get_week_dates(resolved_week_start)
        week_end = week_dates[-1]

        week_data = {"days": []}
        week_scores = []
        for day in week_dates:
            targets_row = conn.execute(
                "SELECT * FROM daily_targets WHERE athlete_id = ? AND target_date = ?",
                (athlete_id, day),
            ).fetchone()
            meals = conn.execute(
                "SELECT * FROM meal_logs WHERE athlete_id = ? AND DATE(logged_at) = ?",
                (athlete_id, day),
            ).fetchall()
            meal_list = [dict(m) for m in meals]
            week_data["days"].append({
                "date": day,
                "targets": dict(targets_row) if targets_row else None,
                "meals_logged": len(meal_list),
                "total_calories": sum(m.get("calories") or 0 for m in meal_list),
                "total_carbs_g": sum(m.get("carbs_g") or 0 for m in meal_list),
                "total_protein_g": sum(m.get("protein_g") or 0 for m in meal_list),
                "total_iron_mg": sum(m.get("iron_mg") or 0 for m in meal_list),
                "total_calcium_mg": sum(m.get("calcium_mg") or 0 for m in meal_list),
                "total_water_oz": sum(m.get("water_oz") or 0 for m in meal_list),
            })
            if targets_row and meal_list:
                from api.services.today_service import compute_logged_totals, compute_traffic_light
                logged = compute_logged_totals(meal_list)
                tl = compute_traffic_light(dict(targets_row), logged)
                week_scores.append(tl["daily_fuel_score"])

        report = claude_ai.prompt3_weekly_report(athlete, week_data)
        report["athlete_id"] = athlete_id
        report["week_start"] = resolved_week_start
        report["week_end"] = week_end
        computed_score = round(sum(week_scores) / len(week_scores)) if week_scores else report.get("weekly_fuel_score", 0)
        report["letter_grade"] = calc_letter_grade(computed_score)
        return report
    finally:
        conn.close()
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && python -c "from api.routes.reports import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add api/routes/reports.py
git commit -m "feat(api): add week_start param and letter_grade to weekly report endpoint"
```

---

## Task 4: WeekNav component

**Files:**
- Create: `frontend/src/components/nutrition/WeekNav.jsx`

- [ ] **Step 1: Create directory and file**

```jsx
export default function WeekNav({ weekStart, weekEnd, daysLogged, isCurrentWeek, onPrev, onNext }) {
  function fmt(iso) {
    if (!iso) return "—";
    const [, m, d] = iso.split("-");
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${months[+m - 1]} ${+d}`;
  }
  const year = weekStart ? weekStart.slice(0, 4) : "";
  const label = `${fmt(weekStart)} – ${fmt(weekEnd)}, ${year}`;
  const sub = isCurrentWeek
    ? `Current week · ${daysLogged} day${daysLogged !== 1 ? "s" : ""} logged`
    : `Past week · ${daysLogged} day${daysLogged !== 1 ? "s" : ""} logged`;

  return (
    <div style={s.strip}>
      <div>
        <div style={s.label}>{label}</div>
        <div style={s.sub}>{sub}</div>
      </div>
      <div style={s.arrows}>
        <button style={s.arrow} onClick={onPrev} aria-label="Previous week">‹</button>
        <button
          style={{ ...s.arrow, opacity: isCurrentWeek ? 0.35 : 1 }}
          onClick={onNext}
          disabled={isCurrentWeek}
          aria-label="Next week"
        >›</button>
      </div>
    </div>
  );
}

const s = {
  strip: {
    background: "#fff", borderBottom: "1px solid #dce8e0",
    padding: "10px 16px 8px", display: "flex", alignItems: "center",
    justifyContent: "space-between",
  },
  label: {
    fontSize: "14px", fontWeight: "700", color: "#1b3a2a",
    letterSpacing: "-.01em", fontFamily: "'Nunito', sans-serif",
  },
  sub: { fontSize: "12px", color: "#8aa898", marginTop: "1px" },
  arrows: { display: "flex", gap: "6px" },
  arrow: {
    width: "28px", height: "28px", border: "1px solid #dce8e0", borderRadius: "6px",
    background: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
    fontSize: "16px", color: "#4a6358", cursor: "pointer",
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/nutrition/WeekNav.jsx
git commit -m "feat(ui): add WeekNav component for Fuel Report week navigation"
```

---

## Task 5: WinHero component

**Files:**
- Create: `frontend/src/components/nutrition/WinHero.jsx`

- [ ] **Step 1: Create file**

```jsx
const NUTRIENT_LABELS = {
  iron_mg: "🩸 Iron", calcium_mg: "🦴 Calcium", carbs_g: "⚡ Carbs",
  protein_g: "💪 Protein", calories: "🔥 Calories", water_oz: "💧 Hydration",
};

const FOCUS_TIPS = {
  iron_mg:    "Lentils or lean beef at lunch will move this fast.",
  calcium_mg: "2 glasses of milk or yogurt closes most of this gap.",
  water_oz:   "A water bottle at school + one at practice does it.",
  carbs_g:    "Rice, pasta, or oats at every main meal.",
  calories:   "Don't skip snacks — add a recovery meal after training.",
  protein_g:  "Add Greek yogurt or eggs to breakfast.",
};

const UNIT = {
  iron_mg: "mg", calcium_mg: "mg", carbs_g: "g",
  protein_g: "g", calories: " kcal", water_oz: "oz",
};

const COLOR_BOX = {
  gold:   "rgba(217,119,6,.12)",
  green:  "rgba(45,106,79,.12)",
  blue:   "rgba(37,99,235,.10)",
  purple: "rgba(126,106,181,.12)",
  red:    "rgba(184,58,58,.10)",
};

export default function WinHero({ athlete, weekSummary }) {
  const {
    week_fuel_score: score = 0,
    prev_week_score: prevScore = null,
    streak = {},
    wins = [],
    ranked_gaps: gaps = [],
    days_logged: daysLogged = 0,
  } = weekSummary;

  if (daysLogged === 0) {
    return (
      <div style={s.card}>
        <div style={s.banner}>
          <div style={s.eyebrow}>🏆 This week's performance</div>
          <div style={s.headline}>{athlete.first_name} is on the way.</div>
          <div style={s.sub}>Log the first meal of the week to unlock your weekly fuel report.</div>
        </div>
      </div>
    );
  }

  const delta = prevScore !== null ? score - prevScore : null;
  const deltaStr = delta === null ? "—" : delta >= 0 ? `↑${delta}` : `↓${Math.abs(delta)}`;
  const focusGaps = gaps.slice(0, 2);

  return (
    <div style={s.card}>
      <div style={s.banner}>
        <div style={s.eyebrow}>🏆 This week's performance</div>
        <div style={s.headline}>{athlete.first_name} is building{"\n"}great habits.</div>
        <div style={s.sub}>
          {streak.current_streak >= 2
            ? `${streak.current_streak} days logged in a row — discipline like this is what separates good athletes from great ones.`
            : "Every meal logged helps fuel better performance. Keep building the habit."}
        </div>
        <div style={s.statsRow}>
          <div style={s.statTile}>
            <div style={s.statVal}>{score}</div>
            <div style={s.statLabel}>Week fuel score</div>
          </div>
          <div style={s.statTile}>
            <div style={s.statVal}>{streak.current_streak ?? 0}🔥</div>
            <div style={s.statLabel}>Day streak</div>
          </div>
          <div style={s.statTile}>
            <div style={s.statVal}>{deltaStr}</div>
            <div style={s.statLabel}>vs last week</div>
          </div>
        </div>
      </div>

      <div style={s.winsList}>
        <div style={s.sectionLabel}>What {athlete.first_name} crushed this week</div>
        {wins.map((win, i) => (
          <div key={i} style={s.winItem}>
            <div style={{ ...s.winIconBox, background: COLOR_BOX[win.color] ?? COLOR_BOX.green }}>
              {win.icon}
            </div>
            <div>
              <div style={s.winLabel}>{win.label}</div>
              <div style={s.winDetail}>{win.detail}</div>
            </div>
          </div>
        ))}
      </div>

      {focusGaps.length > 0 && (
        <div style={s.focusStrip}>
          <div style={s.sectionLabel}>
            {focusGaps.length === 1 ? "One area to build on" : "Two areas to build on this week"}
          </div>
          <div style={s.focusRow}>
            {focusGaps.map((gap) => {
              const pct = gap.avg_pct;
              const color = pct < 50 ? "#b83a3a" : "#b45309";
              const label = NUTRIENT_LABELS[gap.nutrient] ?? gap.nutrient;
              const unit = UNIT[gap.nutrient] ?? "";
              return (
                <div key={gap.nutrient} style={s.focusTile}>
                  <div style={s.ftNutrient}>{label}</div>
                  <div style={{ ...s.ftVal, color }}>{pct}%</div>
                  <div style={s.ftTarget}>avg · target {Math.round(gap.target)}{unit}</div>
                  <div style={s.ftBar}>
                    <div style={{ ...s.ftBarFill, width: `${Math.min(100, pct)}%`, background: color }} />
                  </div>
                  <div style={s.ftTip}>{FOCUS_TIPS[gap.nutrient] ?? "Focus on this nutrient this week."}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const s = {
  card: { background: "#fff", borderRadius: "14px", border: "1px solid #dce8e0", overflow: "hidden" },
  banner: {
    background: "linear-gradient(145deg, #1b3a2a 0%, #2d6a4f 60%, #40916c 100%)",
    padding: "18px 16px 16px",
  },
  eyebrow: {
    fontSize: "12px", fontWeight: "600", textTransform: "uppercase",
    letterSpacing: ".12em", color: "#b7e4c7", marginBottom: "6px",
  },
  headline: {
    fontFamily: "'Nunito', sans-serif", fontSize: "26px", fontWeight: "900",
    color: "#fff", letterSpacing: "-.02em", lineHeight: "1.2",
    marginBottom: "6px", whiteSpace: "pre-line",
  },
  sub: { fontSize: "13px", color: "rgba(255,255,255,.7)", lineHeight: "1.5", marginBottom: "14px" },
  statsRow: { display: "flex", gap: "8px" },
  statTile: {
    flex: 1, background: "rgba(255,255,255,.12)", border: "1px solid rgba(255,255,255,.15)",
    borderRadius: "10px", padding: "10px", textAlign: "center",
  },
  statVal: {
    fontFamily: "'Nunito', sans-serif", fontSize: "22px", fontWeight: "800",
    color: "#fff", lineHeight: "1", marginBottom: "3px",
  },
  statLabel: { fontSize: "10px", color: "rgba(255,255,255,.65)", textTransform: "uppercase", letterSpacing: ".06em" },
  winsList: { padding: "14px 14px 6px" },
  sectionLabel: { fontSize: "11px", textTransform: "uppercase", letterSpacing: ".1em", color: "#8aa898", fontWeight: "600", marginBottom: "10px" },
  winItem: { display: "flex", alignItems: "flex-start", gap: "10px", marginBottom: "10px" },
  winIconBox: { width: "34px", height: "34px", borderRadius: "9px", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "17px" },
  winLabel: { fontSize: "14px", fontWeight: "700", color: "#1b3a2a", lineHeight: "1.3" },
  winDetail: { fontSize: "12px", color: "#4a6358", marginTop: "1px" },
  focusStrip: { borderTop: "1px solid #dce8e0", padding: "12px 14px 14px", background: "#fafcfb" },
  focusRow: { display: "flex", gap: "8px" },
  focusTile: { flex: 1, background: "#fff", border: "1px solid #dce8e0", borderRadius: "10px", padding: "10px" },
  ftNutrient: { fontSize: "13px", color: "#4a6358", fontWeight: "500", marginBottom: "3px" },
  ftVal: { fontFamily: "'Nunito', sans-serif", fontSize: "18px", fontWeight: "800", lineHeight: "1.1", marginBottom: "1px" },
  ftTarget: { fontSize: "10px", color: "#8aa898" },
  ftBar: { height: "2px", background: "#dce8e0", borderRadius: "2px", marginTop: "6px", marginBottom: "5px", overflow: "hidden" },
  ftBarFill: { height: "100%", borderRadius: "2px" },
  ftTip: { fontSize: "11px", color: "#4a6358", fontStyle: "italic", lineHeight: "1.4" },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/nutrition/WinHero.jsx
git commit -m "feat(ui): add WinHero component — celebration-first Zone 1"
```

---

## Task 6: WeeklyHeatmap component

**Files:**
- Create: `frontend/src/components/nutrition/WeeklyHeatmap.jsx`

- [ ] **Step 1: Create file**

```jsx
const NUTRIENTS = [
  { key: "iron_mg",    label: "🩸 Iron" },
  { key: "calcium_mg", label: "🦴 Calcium" },
  { key: "carbs_g",    label: "⚡ Carbs" },
  { key: "protein_g",  label: "💪 Protein" },
  { key: "calories",   label: "🔥 Calories" },
  { key: "water_oz",   label: "💧 Water" },
];

const EVENT_ABBR = {
  game: "GAM", tournament: "TOUR", practice: "PRA",
  strength: "STR", training: "TRN", rest: "RES",
};

const EVENT_COLOR = {
  game: "#c05a4a", tournament: "#7e6ab5", practice: "#c8903a",
  strength: "#1d4ed8", training: "#1d4ed8", rest: "#2d6a4f",
};

function Dot({ pct, isToday }) {
  const base = {
    width: "28px", height: "26px", borderRadius: "5px", display: "flex",
    alignItems: "center", justifyContent: "center", fontSize: "11px",
    fontWeight: "700", margin: "0 auto", fontFamily: "'Nunito', sans-serif",
    ...(isToday ? { outline: "2px solid #2d6a4f", outlineOffset: "1px" } : {}),
  };
  if (pct === null || pct === undefined) {
    return <div style={{ ...base, background: "#f4f8f5", color: "#c8d8d0" }}>—</div>;
  }
  const scheme = pct >= 80
    ? { bg: "rgba(45,106,79,.15)", color: "#2d6a4f" }
    : pct >= 50
    ? { bg: "rgba(217,119,6,.12)", color: "#b45309" }
    : { bg: "rgba(184,58,58,.12)", color: "#b83a3a" };
  return (
    <div style={{ ...base, background: scheme.bg, color: scheme.color }}>
      {pct >= 80 ? "✓" : pct}
    </div>
  );
}

export default function WeeklyHeatmap({ days = [], heatmap = {} }) {
  return (
    <div style={s.card}>
      <div style={s.header}>
        <span style={s.eyebrow}>Weekly nutrient heatmap</span>
        <span style={s.right}>color = % of target</span>
      </div>
      <div style={s.grid}>
        <div style={s.row}>
          <div style={s.labelCell} />
          {days.map((day) => (
            <div key={day.date} style={s.headerCell}>
              <span style={{ ...s.dayAbbr, color: day.is_today ? "#2d6a4f" : "#4a6358" }}>
                {day.day_abbr}
              </span>
              {day.event_type && (
                <span style={{ ...s.eventBadge, color: EVENT_COLOR[day.event_type] ?? "#4a6358" }}>
                  {EVENT_ABBR[day.event_type] ?? day.event_type.slice(0, 3).toUpperCase()}
                </span>
              )}
            </div>
          ))}
        </div>

        {NUTRIENTS.map(({ key, label }) => (
          <div key={key} style={s.row}>
            <div style={s.labelCell}>{label}</div>
            {days.map((day, i) => (
              <Dot key={day.date} pct={heatmap[key]?.[i] ?? null} isToday={day.is_today} />
            ))}
          </div>
        ))}

        <div style={{ ...s.row, borderTop: "1px solid #dce8e0", marginTop: "4px", paddingTop: "6px" }}>
          <div style={{ ...s.labelCell, fontSize: "10px", textTransform: "uppercase", letterSpacing: ".06em", color: "#8aa898", fontWeight: "600" }}>
            Fuel Score
          </div>
          {days.map((day) => {
            const sc = day.score;
            const color = sc == null ? "#c8d8d0" : sc >= 75 ? "#2d6a4f" : sc >= 50 ? "#b45309" : "#b83a3a";
            return (
              <div key={day.date} style={{
                width: "28px", height: "26px", borderRadius: "5px", margin: "0 auto",
                background: "#f4f8f5", color, fontWeight: day.is_today ? "800" : "700",
                fontSize: day.is_today ? "13px" : "11px", display: "flex",
                alignItems: "center", justifyContent: "center",
                fontFamily: "'Nunito', sans-serif",
                ...(day.is_today ? { outline: "2px solid #2d6a4f", outlineOffset: "1px" } : {}),
              }}>
                {sc ?? "—"}
              </div>
            );
          })}
        </div>
      </div>

      <div style={s.legend}>
        <span style={{ ...s.legendDot, background: "rgba(45,106,79,.15)", color: "#2d6a4f" }}>✓</span> ≥80%
        <span style={{ ...s.legendDot, background: "rgba(217,119,6,.12)", color: "#b45309", marginLeft: "10px" }}>65</span> 50–79%
        <span style={{ ...s.legendDot, background: "rgba(184,58,58,.12)", color: "#b83a3a", marginLeft: "10px" }}>35</span> &lt;50%
        <span style={{ ...s.legendDot, background: "#f4f8f5", color: "#c8d8d0", marginLeft: "10px" }}>—</span> Not logged
      </div>
    </div>
  );
}

const s = {
  card: { background: "#fff", borderRadius: "14px", border: "1px solid #dce8e0", overflow: "hidden" },
  header: { padding: "11px 14px 10px", borderBottom: "1px solid #dce8e0", display: "flex", justifyContent: "space-between", alignItems: "center" },
  eyebrow: { fontSize: "11px", textTransform: "uppercase", letterSpacing: ".1em", color: "#2d6a4f", fontWeight: "600" },
  right: { fontSize: "10px", color: "#8aa898" },
  grid: { padding: "10px 8px 10px" },
  row: { display: "grid", gridTemplateColumns: "72px repeat(7, 1fr)", gap: "3px", marginBottom: "3px", alignItems: "center" },
  labelCell: { fontSize: "12px", color: "#4a6358", fontWeight: "500" },
  headerCell: { display: "flex", flexDirection: "column", alignItems: "center", gap: "1px" },
  dayAbbr: { fontSize: "11px", fontWeight: "700" },
  eventBadge: { fontSize: "9px", fontWeight: "600", letterSpacing: ".04em" },
  legend: { borderTop: "1px solid #dce8e0", padding: "8px 12px", fontSize: "11px", color: "#8aa898", display: "flex", alignItems: "center", gap: "4px" },
  legendDot: { width: "20px", height: "18px", borderRadius: "4px", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: "10px", fontWeight: "700" },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/nutrition/WeeklyHeatmap.jsx
git commit -m "feat(ui): add WeeklyHeatmap component — 6-nutrient × 7-day grid"
```

---

## Task 7: ParentReport component

**Files:**
- Create: `frontend/src/components/nutrition/ParentReport.jsx`

- [ ] **Step 1: Create file**

```jsx
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
      .then((r) => { if (!r.ok) throw new Error("Could not load report"); return r.json(); })
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
          <p style={s.loadingSub}>Analysing 7 days of nutrition data — usually takes 10–20 seconds.</p>
        </div>
      </div>
    );
  }
  if (error || !report) return null;

  const grade = report.letter_grade ?? "—";
  const whatWentWell = Array.isArray(report.what_went_well) ? report.what_went_well : [];
  const focusAreas = Array.isArray(report.nutrients_to_focus_on) ? report.nutrients_to_focus_on.slice(0, 1) : [];
  const actions = Array.isArray(report.nutrients_to_focus_on) ? report.nutrients_to_focus_on.slice(0, 2) : [];
  const featuredRecipe = report.featured_recipe ?? null;
  const gameReadiness = report.game_day_readiness ?? null;

  return (
    <div style={s.card}>
      <div style={s.header}>
        <div>
          <div style={s.title}>Weekly Fuel Report</div>
          <div style={s.sub}>AI-generated · science-backed</div>
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
            <div style={s.alertTitle}>{focusAreas[0].nutrient} — {focusAreas[0].gap}</div>
            <div style={s.alertBody}>{(focusAreas[0].food_fixes ?? []).join(" · ")}</div>
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
              {a.recipe && <div style={s.actionRecipe}>Suggested: {a.recipe}</div>}
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
  card: { background: "#fff", borderRadius: "14px", border: "1px solid #dce8e0", overflow: "hidden" },
  header: { padding: "14px 16px 12px", borderBottom: "1px solid #dce8e0", display: "flex", justifyContent: "space-between", alignItems: "flex-start" },
  title: { fontFamily: "'Nunito', sans-serif", fontSize: "16px", fontWeight: "800", color: "#1b3a2a" },
  sub: { fontSize: "11px", color: "#8aa898", marginTop: "2px" },
  gradeBlock: { textAlign: "center", flexShrink: 0 },
  grade: { fontFamily: "'Nunito', sans-serif", fontSize: "18px", fontWeight: "900", color: "#2d6a4f" },
  gradeSub: { fontSize: "10px", color: "#8aa898", textTransform: "uppercase", letterSpacing: ".06em" },
  loadingBody: { padding: "32px 16px", textAlign: "center" },
  spinner: {
    width: "32px", height: "32px", borderRadius: "50%", margin: "0 auto 12px",
    border: "3px solid #dce8e0", borderTopColor: "#2d6a4f",
    animation: "spin 0.8s linear infinite",
  },
  loadingText: { fontSize: "14px", color: "#1b3a2a", fontWeight: "600", margin: "0 0 4px" },
  loadingSub: { fontSize: "12px", color: "#8aa898", margin: 0 },
  section: { padding: "12px 16px", borderBottom: "1px solid #f4f8f5" },
  sectionLabel: { fontSize: "11px", textTransform: "uppercase", letterSpacing: ".1em", color: "#8aa898", fontWeight: "600", marginBottom: "8px" },
  positiveItem: { display: "flex", alignItems: "flex-start", gap: "8px", marginBottom: "6px" },
  checkBox: { width: "20px", height: "20px", borderRadius: "6px", background: "rgba(45,106,79,.12)", color: "#2d6a4f", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "12px", fontWeight: "700", flexShrink: 0, marginTop: "1px" },
  posText: { fontSize: "13px", color: "#1b3a2a", lineHeight: "1.5" },
  alertBox: { background: "rgba(217,119,6,.06)", border: "1px solid rgba(217,119,6,.2)", borderRadius: "10px", padding: "10px 12px" },
  alertTitle: { fontSize: "13px", fontWeight: "700", color: "#b45309", marginBottom: "4px" },
  alertBody: { fontSize: "12px", color: "#4a6358", lineHeight: "1.5" },
  actionItem: { background: "#f4f8f5", borderRadius: "8px", padding: "10px", marginBottom: "6px" },
  actionNutrient: { fontSize: "12px", fontWeight: "700", color: "#2d6a4f", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: "3px" },
  actionBody: { fontSize: "13px", color: "#1b3a2a", lineHeight: "1.5" },
  actionRecipe: { fontSize: "11px", color: "#8aa898", marginTop: "4px", fontStyle: "italic" },
  recipeRow: { display: "flex", gap: "10px", alignItems: "flex-start", background: "rgba(45,106,79,.06)", border: "1px solid rgba(45,106,79,.15)", borderRadius: "10px", padding: "10px 12px" },
  recipeIcon: { fontSize: "20px", flexShrink: 0 },
  recipeName: { fontSize: "13px", fontWeight: "700", color: "#1b3a2a", marginBottom: "2px" },
  recipeWhy: { fontSize: "12px", color: "#4a6358", lineHeight: "1.4" },
  readinessText: { fontSize: "13px", color: "#1b3a2a", lineHeight: "1.6" },
};
```

- [ ] **Step 2: Add CSS animation for spinner**

The spinner `animation: "spin 0.8s linear infinite"` requires a keyframe. Open `frontend/src/index.css` (or equivalent global CSS) and add if not already present:

```css
@keyframes spin {
  to { transform: rotate(360deg); }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/nutrition/ParentReport.jsx
git commit -m "feat(ui): add ParentReport component — AI-generated weekly Zone 3"
```

---

## Task 8: Rewrite NutritionDashboard.jsx

**Files:**
- Rewrite: `frontend/src/NutritionDashboard.jsx`

- [ ] **Step 1: Replace entire file**

```jsx
import { useState, useEffect, useCallback } from "react";
import WeekNav from "./components/nutrition/WeekNav";
import WinHero from "./components/nutrition/WinHero";
import WeeklyHeatmap from "./components/nutrition/WeeklyHeatmap";
import ParentReport from "./components/nutrition/ParentReport";

const API = import.meta.env.VITE_API_URL ?? "";

function getWeekStart(isoDate) {
  const d = new Date(isoDate + "T12:00:00");
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
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
      const res = await fetch(`${API}/api/athletes/${athlete.id}/weekly-summary?week_start=${weekStart}`);
      if (!res.ok) throw new Error("Failed to load weekly summary.");
      setSummary(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [athlete.id, weekStart]);

  useEffect(() => { load(); }, [load]);

  return (
    <div style={s.page}>
      <WeekNav
        weekStart={weekStart}
        weekEnd={summary?.week_end ?? weekStart}
        daysLogged={summary?.days_logged ?? 0}
        isCurrentWeek={isCurrentWeek}
        onPrev={() => setWeekStart((ws) => addWeeks(ws, -1))}
        onNext={() => { if (!isCurrentWeek) setWeekStart((ws) => addWeeks(ws, 1)); }}
      />

      {loading && (
        <div style={s.center}>
          <p style={s.loadingText}>Loading week data…</p>
        </div>
      )}
      {!loading && error && (
        <div style={s.center}>
          <p style={{ color: "#b83a3a", fontSize: "14px" }}>{error}</p>
          <button style={s.retryBtn} onClick={load}>Retry</button>
        </div>
      )}

      {!loading && summary && (
        <div style={s.body}>
          <WinHero athlete={athlete} weekSummary={summary} />
          <WeeklyHeatmap days={summary.days} heatmap={summary.heatmap} />
          <ParentReport athleteId={athlete.id} weekStart={weekStart} />
          <p style={s.disclaimer}>
            AthFuelPath provides food education guidance — not medical nutrition therapy.
            Consult your physician or a licensed RDN for medical nutrition concerns.
          </p>
        </div>
      )}
    </div>
  );
}

const s = {
  page: { fontFamily: "'Nunito', 'DM Sans', sans-serif", background: "#f4f8f5", minHeight: "100vh" },
  body: { padding: "12px 12px 80px", display: "flex", flexDirection: "column", gap: "10px" },
  center: { display: "flex", flexDirection: "column", alignItems: "center", padding: "48px 16px" },
  loadingText: { fontSize: "15px", color: "#4a6358" },
  retryBtn: {
    marginTop: "8px", padding: "8px 20px", borderRadius: "8px",
    background: "#2d6a4f", color: "#fff", border: "none", fontSize: "14px",
    fontWeight: "600", cursor: "pointer",
  },
  disclaimer: {
    textAlign: "center", fontSize: "12px", color: "#8aa898",
    lineHeight: "1.5", paddingTop: "8px",
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/NutritionDashboard.jsx
git commit -m "feat(ui): rewrite NutritionDashboard as Fuel Report tab (Zones 1-3)"
```

---

## Task 9: Verify end-to-end

- [ ] **Step 1: Start backend**

```bash
cd /Users/mayurkhera/AthFuelPath && source venv/bin/activate && uvicorn api.main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend**

```bash
cd /Users/mayurkhera/AthFuelPath/frontend && npm run dev
```

- [ ] **Step 3: Verify backend endpoint**

```bash
curl -s "http://localhost:8000/api/athletes/1/weekly-summary" | python3 -m json.tool | head -40
```

Expected: JSON with `week_start`, `days`, `heatmap`, `wins`, `ranked_gaps` keys.

- [ ] **Step 4: Check UI**

Open `http://localhost:5173`, log in, tap "Fuel Report" tab. Confirm:
- Week navigation strip shows current week
- Dark green banner shows athlete name and streak
- Wins list shows at least 1 win
- Heatmap grid renders 6 rows × 7 columns
- Parent Report card loads (shows spinner then content)

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Fuel Report tab — celebration-first weekly view (Zones 1-3)"
```
