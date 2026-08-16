# AthFuelPath — React Native / Expo Mobile Build Plan

**Prepared by:** Senior Mobile React Engineer audit  
**Date:** 2026-06-11  
**Backend target:** `https://fuelup-youth.fly.dev` (FastAPI + SQLite on Fly.io)  
**Audience:** Claude Code execution instructions — each phase must produce a verifiable, runnable result before the next phase begins.

---

## Repository Recommendation: Separate Repo

**Verdict: Create a new, standalone repository for the mobile app.**

### Why NOT a monorepo with the current backend repo

The current repo (`AthFuelPath/`) is a tightly coupled Python/React web monolith:

- The Dockerfile builds the Vite web bundle INTO the Python container. The mobile app has no relationship with that build pipeline.
- React Native requires Expo CLI, Metro bundler, EAS Build, and `node_modules` entirely different from the web frontend's Vite setup. Mixing them creates tooling conflicts.
- Deployment paths are completely different: web deploys via `fly deploy`; mobile deploys via EAS Build → App Store Connect / Google Play. Different CI secrets, different workflows.
- The backend is already a clean REST API with CORS wide open (`allow_origins=["*"]`). It is already architected to serve any client — the mobile app is simply a new consumer of the same API.
- Independent versioning: v1.2 of the mobile app should be releasable without touching backend code. A monorepo couples those release cycles.

### Recommended structure

```
AthFuelPath/                  ← existing repo (unchanged)
  api/
  frontend/
  ...

AthFuelPath-mobile/           ← new repo
  app/
  components/
  services/
  store/
  ...
```

The mobile repo references the live production API via a single `API_BASE_URL` environment variable. Local dev points to the developer's local uvicorn instance.

---

## Backend Reference During Development

This is the most operationally important section for day-to-day mobile development. Mobile devices and simulators cannot reach `localhost` the same way a browser on your laptop can. Each runtime context needs a different address to find the backend.

### The core problem

When you type `http://localhost:8000` in a mobile context:
- **iOS Simulator** → resolves correctly to your Mac's loopback. ✅
- **Android Emulator** → `localhost` means the *emulator's own* loopback, not your machine. ❌ Use `http://10.0.2.2:8000` instead.
- **Physical device on WiFi** → `localhost` is meaningless. The device has no idea where your laptop is. ❌ Use your machine's LAN IP (e.g., `http://192.168.1.45:8000`).
- **EAS cloud build / production** → must point to the live server. ✅ `https://fuelup-youth.fly.dev`

### Decision: Use production API as the primary dev target

For this project, **default all mobile development to point at the live production API** (`https://fuelup-youth.fly.dev`). Rationale:

- The backend is already deployed, stable, and has real seed data.
- CORS is already wide open (`allow_origins=["*"]`) — no blocked requests.
- The production API runs over HTTPS, which is required for certain Expo features (camera permissions, push notifications) and avoids iOS ATS (App Transport Security) warnings.
- It eliminates the three-address problem above — one URL works everywhere.
- The backend and mobile repos are now decoupled: a mobile developer does not need Python, a venv, or SQLite tooling installed.

Use a local backend **only when actively developing a new or changed API endpoint** before it has been deployed.

### Environment configuration

**Step 1 — Create environment files in the mobile repo root:**

```bash
# .env                     ← production (used by EAS Build, CI, and physical device testing)
EXPO_PUBLIC_API_URL=https://fuelup-youth.fly.dev

# .env.local               ← local development override (gitignored)
# Uncomment the line that matches your current context:
# EXPO_PUBLIC_API_URL=http://localhost:8000          # iOS Simulator only
# EXPO_PUBLIC_API_URL=http://10.0.2.2:8000           # Android Emulator only
# EXPO_PUBLIC_API_URL=http://192.168.1.XX:8000       # Physical device (replace XX with your machine's LAN IP)
```

`.env` is committed. `.env.local` is gitignored and overrides `.env` locally for Expo (Expo reads `.env.local` first via Metro's dotenv resolution).

**Step 2 — Single API constant in the codebase:**

```ts
// constants/api.ts
export const API_BASE = process.env.EXPO_PUBLIC_API_URL ?? "https://fuelup-youth.fly.dev";
```

Every `fetch` in the app goes through this. Never hardcode a URL anywhere else.

**Step 3 — API wrapper with the base URL baked in:**

```ts
// services/api.ts
import { API_BASE } from "../constants/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get:    <T>(path: string)                  => request<T>(path),
  post:   <T>(path: string, body: unknown)   => request<T>(path, { method: "POST",   body: JSON.stringify(body) }),
  put:    <T>(path: string, body: unknown)   => request<T>(path, { method: "PUT",    body: JSON.stringify(body) }),
  delete: <T>(path: string)                  => request<T>(path, { method: "DELETE" }),
};
```

### Finding your machine's LAN IP (when you need local backend)

```bash
# macOS
ipconfig getifaddr en0       # Wi-Fi
ipconfig getifaddr en1       # Ethernet (less common)

# Or check System Settings → Wi-Fi → Details → IP Address
```

Update `.env.local` with that IP. Note: it changes if you move networks or your router reassigns your DHCP lease. When it changes, update the file and restart Metro (`r` in the Expo terminal).

### When to switch to a local backend

Only switch to a local backend when you are **actively building or modifying a backend endpoint** before deploying it. The workflow is:

1. Make the backend change in the `AthFuelPath/` repo.
2. Start the local server: `source venv/bin/activate && uvicorn api.main:app --reload --port 8000`
3. Switch `.env.local` to your local address (see table above for your device type).
4. Restart Metro: `npx expo start --clear`
5. Test the new endpoint in the mobile app.
6. Commit and deploy the backend change: `fly deploy -a fuelup-youth`
7. Switch `.env.local` back to the production URL (or delete it entirely to use the default).

The two backend changes required by this mobile build plan (Expo push token endpoint, `logged_at` on meal logs) should be **deployed to production before Phase 12 begins**. That way the mobile developer never needs a local backend for those phases.

### Using ngrok as an alternative (optional)

If you need a single stable URL that works across iOS Simulator + Android Emulator + physical devices simultaneously without knowing your LAN IP:

```bash
# Install ngrok (one-time)
brew install ngrok
ngrok config add-authtoken YOUR_NGROK_TOKEN   # free account at ngrok.com

# Expose local backend
ngrok http 8000
# Output: Forwarding https://abc123.ngrok-free.app → localhost:8000
```

Set `EXPO_PUBLIC_API_URL=https://abc123.ngrok-free.app` in `.env.local`. The ngrok URL is valid for the lifetime of that terminal session (free tier: URL changes on restart; paid tier: stable custom domain).

Use this when running a local backend is necessary and you are testing on a physical device.

### Summary table

| Where you're running | Backend target | `.env.local` value |
|---|---|---|
| iOS Simulator + production API (default) | `fuelup-youth.fly.dev` | _(delete `.env.local`)_ |
| iOS Simulator + local backend | `localhost:8000` | `http://localhost:8000` |
| Android Emulator + local backend | `10.0.2.2:8000` | `http://10.0.2.2:8000` |
| Physical device on WiFi + local backend | Your machine's LAN IP | `http://192.168.1.XX:8000` |
| Physical device + production API (default) | `fuelup-youth.fly.dev` | _(delete `.env.local`)_ |
| EAS Build (TestFlight / internal track) | `fuelup-youth.fly.dev` | Set as EAS secret, not `.env.local` |
| EAS Build (staging, future) | staging URL | Set as EAS secret per build profile |

### EAS Build secrets

For cloud builds, environment variables are set in EAS — not in `.env.local` (which is gitignored and not uploaded):

```bash
eas secret:create --scope project --name EXPO_PUBLIC_API_URL --value "https://fuelup-youth.fly.dev"
```

Or in `eas.json` per build profile:

```json
{
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "env": { "EXPO_PUBLIC_API_URL": "https://fuelup-youth.fly.dev" }
    },
    "preview": {
      "distribution": "internal",
      "env": { "EXPO_PUBLIC_API_URL": "https://fuelup-youth.fly.dev" }
    },
    "production": {
      "env": { "EXPO_PUBLIC_API_URL": "https://fuelup-youth.fly.dev" }
    }
  }
}
```

---

## System Audit Summary

### Backend API surface (all consumed by mobile)

| Router prefix | Key endpoints used by mobile | Notes |
|---|---|---|
| `POST /api/parents` | Account creation | OTP-less creation, consent required |
| `POST /api/parents/request-otp` | Auth | Rate-limited 60s |
| `POST /api/parents/verify-otp` | Auth | Returns `{parent, athletes}` |
| `POST /api/parents/login` | Login check | Returns parent + athletes without OTP |
| `GET /api/athletes/:id` | Profile | Full athlete row |
| `POST /api/athletes/` | Create athlete | Triggers blueprint generation |
| `PUT /api/athletes/:id` | Update profile | — |
| `GET /api/athletes/:id/blueprint` | Blueprint tab | Returns AI + calculated targets |
| `GET /api/athletes/:id/daily-summary` | Today tab | Master endpoint — event_type, mission_items, traffic_light, forecast |
| `GET /api/athletes/:id/weekly-summary` | Reports | Heatmap, scores, wins |
| `GET/POST /api/events/athlete/:id` | Schedule tab | — |
| `DELETE /api/events/:id` | Schedule tab | — |
| `GET /api/events/fetch-ics` | Calendar import | Returns raw ICS string |
| `GET /api/nutrition/targets/:id` | Nutrition tab | Saves targets to DB |
| `POST /api/meals/` | Meal logging | Body: `{athlete_id, log_method, description, ...macros}` |
| `GET /api/meals/athlete/:id` | Meal log history | Query param: `?date=YYYY-MM-DD` (optional) |
| `GET /api/meal-plans/:id` | Meal planner week | Query param: `?week_start=YYYY-MM-DD` (optional, defaults to current week) |
| `PUT /api/meal-plans/:id/slot` | Assign recipe to slot | Body: `{plan_date, slot_name, recipe_id}` — PUT not POST |
| `DELETE /api/meal-plans/:id/slot` | Clear a slot | Query params: `?plan_date=&slot_name=` |
| `POST /api/meal-plans/:id/log-slot` | Log a planned slot | Body: `{plan_date, slot_name}` — note: `/log-slot` not `/log` |
| `POST /api/meal-plans/generate` | AI meal plan | Body: `{athlete_id, week_start, overwrite_existing}` — no `:id` in path |
| `GET /api/recipes/` | Recipe browser | Filterable by category + dietary |
| `GET /api/recipes/categories` | Recipe categories list | — |
| `GET /api/recipes/:id` | Recipe detail | — |
| `POST /api/recipes/swap` | AI swap | Picky eater alternative |
| `GET /api/water-log/:id/today` | Hydration | — |
| `POST /api/water-log/` | Log water | Body: `{athlete_id, cups, date?}` |
| `GET /api/nutrition/targets/:id` | Compute + save targets | Also writes to `daily_targets` table |
| `POST /api/nutrition/sweat` | Sweat output calc | Body: `{athlete_id, event_id, city}` — path is `/sweat` not `/sweat-output` |
| `POST /api/nutrition/estimate` | AI macro estimate from text | Body: `{athlete_id, description}` — useful for text meal logging |
| `GET /api/analysis/:id` | Gap analysis | Claude-powered nutrient gap |
| `GET /api/reports/:id/daily` | Fuel score + badge | — |
| `GET /api/reports/:id/weekly` | Weekly report | — |
| `GET /api/library/articles` | Article list | Query params: `?category=&search=` — path is `/articles` not `/` |
| `GET /api/library/articles/:id` | Article detail | Markdown body — path is `/articles/:id` not `/:id` |
| `GET /api/library/picks/:id` | Alex's Picks for athlete | Returns personalized weekly picks |
| `POST /api/knowledge/ask` | AI Q&A | Body: `{question, athlete_id}` — POST not GET |
| `GET /api/legal/:slug` | Legal docs | Slugs: `terms-of-service`, `privacy-policy` |

### Auth model (important for mobile)
- **No JWT tokens.** The API returns `{parent, athletes}` on successful OTP verify. There is no bearer token.
- Mobile app must persist `parent_id` and selected `athlete_id` in secure local storage and send them as path parameters / body fields in every request.
- `POST /api/parents/login` accepts `{email}` and returns parent + athletes without OTP — useful for re-validating a cached session on app launch.

### Push notifications gap
- The current backend uses **Web Push / VAPID** (`pywebpush`). This does not work with native mobile.
- **Phase 12 requires one new backend endpoint:** `POST /api/notifications/expo-token` to store Expo push tokens alongside the existing VAPID subscriptions.

### Screens to build (mapped from web)

| Web screen | Mobile tab/screen | Priority |
|---|---|---|
| Login (OTP) | Auth stack | P0 |
| Onboarding | Onboarding stack | P0 |
| Today (Home) | Today tab | P0 |
| Meal Planner | Meal Plan tab | P1 |
| Schedule | Schedule tab | P1 |
| Nutrition Dashboard | Fuel Report tab | P1 |
| Hydration | Hydration tab | P2 |
| Recipes | Recipes tab | P2 |
| Library | Library tab | P2 |
| Blueprint | Blueprint screen | P2 |
| Settings / Profile | Settings tab | P2 |
| Notifications | Settings > Notifications | P3 |

---

## Technology Stack

```
Runtime:        Expo SDK 53 (managed workflow)
Navigation:     Expo Router v4 (file-based — Stack + Tabs)
State (server): TanStack Query v5 (caching, refetch, loading states)
State (client): Zustand v5 (session: parent_id, athlete_id, athlete object)
Persistence:    expo-secure-store (session) + AsyncStorage (non-sensitive prefs)
Styling:        React Native StyleSheet (no UI library — match web brand exactly)
Fonts:          expo-font → Nunito + DM Sans (same as web)
Icons:          @expo/vector-icons (Ionicons)
Camera:         expo-camera + expo-image-picker (meal photo logging)
Notifications:  expo-notifications (Expo Push Service replaces VAPID)
Haptics:        expo-haptics
Date handling:  date-fns
Markdown:       react-native-markdown-display (Library tab articles)
Charts:         react-native-svg + victory-native (macro rings, weekly bars)
Testing device: Expo Go (dev) → EAS Build (TestFlight / internal track)
```

**Brand colors (match web exactly):**
```
Primary green:   #2d6a4f
Dark green:      #1b3a2a  
Light green bg:  #f8faf9
Border:          #dce8e0
Text secondary:  #4a6358
Amber:           #b45309
Red:             #9a1a1a
Purple:          #4a2a8a
Font:            Nunito (headings) + DM Sans (body)
```

---

## Phase 0 — Project Bootstrap

**Goal:** New Expo project runs on iOS Simulator and Android Emulator. Connects to the live API and receives a 200 from `/health`.

### Steps

1. Create new GitHub repo: `AthFuelPath-mobile`
2. Scaffold project:
   ```bash
   npx create-expo-app@latest fuelup-mobile --template blank-typescript
   cd fuelup-mobile
   ```
3. Install core dependencies:
   ```bash
   npx expo install expo-router expo-secure-store @react-native-async-storage/async-storage
   npx expo install expo-font expo-haptics expo-notifications expo-camera expo-image-picker
   npm install zustand @tanstack/react-query date-fns react-native-markdown-display
   npm install react-native-svg victory-native
   npm install @expo/vector-icons
   ```
4. Configure `app.json`:
   - `scheme: "athfuelpath"`
   - `bundleIdentifier: "com.fuelupyouth.app"` (iOS)
   - `package: "com.fuelupyouth.app"` (Android)
   - Expo Router `experiments.typedRoutes: true`
5. Create `constants/api.ts`:
   ```ts
   export const API_BASE =
     process.env.EXPO_PUBLIC_API_URL ?? "https://fuelup-youth.fly.dev";
   ```
6. Create `.env.local` for dev: `EXPO_PUBLIC_API_URL=http://localhost:8000`
7. Create `app/index.tsx` that calls `GET /health` on mount and renders the status.
8. Set up `CLAUDE.md` in mobile repo documenting how to run (`npx expo start`), how to build (`eas build`), and API target.

### Verifiable result
- `npx expo start` → app opens in Expo Go on a physical device or simulator
- Screen shows "AthFuelPath" heading and `{"status": "healthy"}` returned from the API
- No TypeScript errors

---

## Phase 1 — Auth Flow

**Goal:** Complete sign-in (OTP) and sign-up (onboarding) flows. Session persisted to `expo-secure-store`. App routes to Today tab on success.

### Screens

```
app/
  (auth)/
    _layout.tsx          ← Stack layout
    index.tsx            ← Welcome / landing screen
    login.tsx            ← Email entry
    verify.tsx           ← OTP code entry (6-digit)
  (onboarding)/
    _layout.tsx
    consent.tsx          ← Age check + COPPA consent text
    profile.tsx          ← Athlete profile form (multi-step)
    review.tsx           ← Review card before submit
    success.tsx          ← Blueprint generating + "You're ready!"
```

### Auth store (`store/authStore.ts`)

```ts
interface AuthState {
  parentId: number | null;
  parent: Parent | null;
  athletes: Athlete[];
  selectedAthleteId: number | null;
  selectedAthlete: Athlete | null;
  setSession: (parent: Parent, athletes: Athlete[]) => void;
  selectAthlete: (id: number) => void;
  signOut: () => void;
}
```

Persist `parentId` + `selectedAthleteId` to `expo-secure-store` on every write. On app launch, rehydrate and call `POST /api/parents/login` with cached email to re-validate session.

### API calls

```
POST /api/parents/request-otp    { email }
POST /api/parents/verify-otp     { email, code }
POST /api/parents                { full_name, email, consent_confirmed: true }
POST /api/athletes/              { parent_id, first_name, age, gender, weight_lbs, ... }
POST /api/parents/login          { email }   ← session rehydration on launch
```

### Onboarding form fields (match web exactly)

- **Step 1 (Age Check):** Athlete age input (9–17 validation)
- **Step 2 (Consent):** Full COPPA text, checkbox to confirm, parent full name + email
- **Step 3 (Profile):** first_name, age, gender, weight_lbs, height_ft, height_in, position (picker), competition_level (picker), sweat_profile (picker), allergies (multi-select), dietary_restrictions (text)
- **Step 4 (Review):** ReviewCard showing all entries
- **Step 5 (Success):** Spinner while blueprint generates, then "Your fuel plan is ready!"

### Verifiable result
- New account: full onboarding creates parent + athlete in production DB, blueprint generated, routes to Today tab
- Existing account: email → OTP email received → 6-digit code → Today tab
- Kill app, reopen → still on Today tab (session persisted)
- Sign out → back to welcome screen, session cleared from secure store

---

## Phase 2 — Navigation Shell

**Goal:** Bottom tab bar with 5 primary tabs. Athlete selector header. Settings accessible from any tab.

### Tab structure

```
app/
  (app)/
    _layout.tsx           ← Tab navigator root
    today/
      index.tsx           ← Today tab (placeholder card)
    meal-plan/
      index.tsx           ← Meal Plan tab (placeholder)
    schedule/
      index.tsx           ← Schedule tab (placeholder)
    nutrition/
      index.tsx           ← Fuel Report tab (placeholder)
    library/
      index.tsx           ← Library tab (placeholder)
    blueprint/
      index.tsx           ← Blueprint (modal stack from tab bar "..." or settings)
    settings/
      index.tsx           ← Settings + sign out
```

### Tab bar design

```
[  Today  ]  [ Meal Plan ]  [ Schedule ]  [ Fuel  ]  [ Library ]
  🏠          🍳             📅            📊          📚
```

Each icon uses `@expo/vector-icons/Ionicons`. Active tab uses `#2d6a4f`. Inactive uses `#4a6358` at 60% opacity. Tab bar background `#ffffff` with `borderTopColor: #dce8e0`.

### Header component

Every tab has a shared header showing:
- AthFuelPath logo text (left)
- Athlete name chip (center) — tappable to switch athlete
- Settings gear icon (right)

Athlete switcher opens a bottom sheet (`@gorhom/bottom-sheet`) listing all athletes under the parent account.

### Verifiable result
- All 5 tabs navigate with no errors
- Tapping athlete chip shows bottom sheet with athlete list
- Selecting different athlete updates `authStore.selectedAthleteId` and re-fetches data on the active tab
- Back gesture/button works within stacks

---

## Phase 3 — Today Tab

**Goal:** The primary daily screen is fully functional: correct event type, mission items matching the meal plan, water logging, fuel score.

### Component tree

```
app/(app)/today/index.tsx
  ├─ BroadcastCard
  │    athlete name + day badge + fuel score ring
  ├─ PerformanceForecast
  │    risk level + description
  ├─ DailyMission
  │    slot checklist (tap to log)
  │    empty state: "Add today's schedule to see your fuel mission"
  ├─ ScienceEdge
  │    iron / calcium / LEA alert cards
  ├─ QuickRow
  │    water cup stepper + calorie bar
  └─ LogMealButton
       navigates to meal logging screen
```

### API

```
GET /api/athletes/:id/daily-summary
```

Response drives all components. Key fields:
- `event_type` → BroadcastCard badge + gradient
- `mission_items[]` → DailyMission list (already slot-synced from Phase 3 backend work)
- `traffic_light` → fuel score, macro indicators
- `performance_forecast` → PerformanceForecast card
- `water_cups` → QuickRow

### Mission item toggle

```
POST /api/meals/
{ athlete_id, log_method: "mission", description: item.label, logged_at: now }
```

Optimistic update: mark item done immediately, rollback on error.

### Water logging

```
POST /api/water-log/
{ athlete_id, cups: newCount }
```

Stepper renders cup icons (filled/empty). Tap + or − triggers debounced POST (500ms). Haptic feedback on each tap.

### Time-based status logic

Port `getMissionStatus()` from web `DailyMission.jsx` exactly. "After HH:MM PM" format handled (NaN → upcoming).

Status → tag: `done → DONE | active → NOW (pulsing) | upcoming → UPCOMING`

### TanStack Query setup

```ts
const { data: summary, refetch } = useQuery({
  queryKey: ["daily-summary", athleteId, today],
  queryFn: () => api.get(`/athletes/${athleteId}/daily-summary`),
  staleTime: 2 * 60 * 1000,  // 2 min
});
```

Pull-to-refresh triggers `refetch()`. App focus event also triggers refetch (same as web `visibilitychange`).

### Verifiable result
- Today tab loads with correct event type (or "Rest Day" if no event)
- Mission items exactly match what Meal Planner shows for the same day
- Tapping a mission item marks it done (checkmark + strikethrough), optimistic update visible immediately
- Water stepper increments/decrements with haptic feedback, persists on reload
- Pull-to-refresh works

---

## Phase 4 — Meal Planner Tab

**Goal:** Week view of meal slots, recipe assignment, AI plan generation, slot logging — feature-parity with web.

### Screens

```
app/(app)/meal-plan/
  index.tsx          ← Week picker + day list
  [date].tsx         ← Day detail (slot list)
  recipe-picker.tsx  ← Recipe picker modal
```

### Week picker

Horizontal scrollable week strip (Mon–Sun). Tapping a day expands its slot list inline or pushes to `[date].tsx`. Day cards show:
- Day badge (event type color + emoji)
- Calorie target vs planned bar
- Slot count filled / total

### Slot card

Each slot shows:
- Icon + display label (e.g., "Pre-Training Fuel")
- Time badge
- Tags (Complex Carbs, Protein, etc.) — colored chips matching web `TAG_COLORS`
- Recipe name (if assigned) or "Tap to add recipe"
- Logged toggle (checkmark)

Tapping a slot with no recipe → opens `recipe-picker.tsx` bottom sheet.
Tapping logged toggle → `POST /api/meal-plans/:id/log-slot { plan_date, slot_name }`.

### Recipe picker

- Filtered to `slot.recipe_category`
- Allergen filter auto-applied from `athlete.allergies`
- Search bar (client-side filter)
- Each card: recipe name, macros, tags
- "AI Suggest Instead" button → `POST /api/recipes/swap`

### AI generate plan

FloatingActionButton in week view → confirmation sheet → `POST /api/meal-plans/generate { athlete_id, week_start, overwrite_existing: false }`. Note: athlete_id goes in the request body, not the URL path. Loading state: per-slot spinners fade in as plan generates.

### API calls

```
GET    /api/meal-plans/:id?week_start=YYYY-MM-DD        ← week_start optional; defaults to current week
PUT    /api/meal-plans/:id/slot   { plan_date, slot_name, recipe_id }   ← PUT not POST
DELETE /api/meal-plans/:id/slot?plan_date=YYYY-MM-DD&slot_name=:name   ← to clear a slot
POST   /api/meal-plans/:id/log-slot  { plan_date, slot_name }           ← /log-slot not /log
POST   /api/meal-plans/generate   { athlete_id, week_start, overwrite_existing }  ← no :id in path
GET    /api/recipes/?category=:cat&avoid_allergens=:allergens
POST   /api/recipes/swap          { athlete_id, disliked_recipe, meal_timing_category }
```

### Verifiable result
- Week view shows all 7 days with correct event types
- Slot cards render with correct labels and tags
- Recipe picker opens, shows filtered recipes, assigns correctly
- Logging a slot updates the logged indicator
- AI generate fills the week (takes ~10–30s — show per-slot loading skeletons)
- Today's Mission on the Today tab reflects slot logging done here

---

## Phase 5 — Schedule Tab

**Goal:** Add, view, and delete training/game events. Events immediately affect Today + Meal Planner.

### Screens

```
app/(app)/schedule/
  index.tsx         ← Calendar + event list
  add-event.tsx     ← Add event form (modal)
```

### Calendar view

Use a horizontal week strip (same pattern as Meal Planner) plus a full list of upcoming events below. Each event card shows:
- Event name + type badge
- Date + time
- Duration
- Delete icon (swipe-to-delete or long-press)

Event types and their display colors (match web `DAY_HERO` colors):
```
rest       → #2d6a4f (green)
practice   → #b45309 (amber)
training   → #b45309 (amber)
strength   → #b45309 (amber)
game       → #9a1a1a (red)
tournament → #4a2a8a (purple)
```

### Add event form

Fields (match web `ScheduleScreen.jsx`):
- Event name (text input)
- Event type (picker: Practice, Game, Tournament, Strength, Rest, Training)
- Date (DateTimePicker)
- Start time (DateTimePicker time mode)
- Duration hours (stepper: 0.5 increments, 0.5–4h)
- City (optional text input)

### ICS import

"Import from calendar" button → `expo-document-picker` for `.ics` files OR accept a calendar URL → `GET /api/events/fetch-ics?url=...` → parse ICS client-side (use `ical.js` npm package) → batch `POST /api/events/` for each event in range.

### API calls

```
GET    /api/events/athlete/:id
GET    /api/events/athlete/:id?date=YYYY-MM-DD
POST   /api/events/                 { athlete_id, event_name, event_type, event_date, start_time, duration_hours, city }
DELETE /api/events/:id
GET    /api/events/fetch-ics?url=:url
```

### Verifiable result
- Add a practice event for tomorrow → Meal Planner for that day switches from Rest to Practice slots
- Today tab shows correct event type when today has an event
- Delete event → Today tab reverts to Rest
- Event list sorts by date ascending

---

## Phase 6 — Fuel Report (Nutrition) Tab

**Goal:** Macro rings, traffic light indicators, gap analysis, weekly heatmap — full nutrition dashboard.

### Screens

```
app/(app)/nutrition/
  index.tsx        ← Daily view (default)
  weekly.tsx       ← Weekly summary (tab within screen)
```

### Daily view components

**MacroRings** — Four circular progress rings (SVG via `react-native-svg`):
- Calories: logged / target
- Carbs (g)
- Protein (g)
- Fat (g)

Color: green if ≥ 80%, amber if 50–79%, red if < 50%.

**MicroIndicators** — Iron and calcium badges (logged mg / target mg).

**TrafficLightCards** — Each macro has a card with: status dot (green/amber/red), logged value, target range, gap message.

**GapAnalysis** — "Get AI Analysis" button → `GET /api/analysis/:id` → renders Claude-generated gap rows.

**LetterGrade** — Large grade letter (A/B/C/D/F) with badge and message.

### Weekly view

- 7-day score heatmap (color-coded squares)
- Streak counter
- Wins list
- Previous week comparison

### API calls

```
GET /api/athletes/:id/daily-summary                    ← primary data source (reused from Today)
GET /api/athletes/:id/weekly-summary?week_start=YYYY-MM-DD
GET /api/nutrition/targets/:id?date=YYYY-MM-DD         ← also writes computed targets to daily_targets table
GET /api/analysis/:id?date=YYYY-MM-DD                  ← on-demand AI gap analysis
GET /api/reports/:id/daily?date=YYYY-MM-DD             ← fuel score badge + message
GET /api/reports/:id/weekly?week_start=YYYY-MM-DD      ← weekly summary badge
```

### Verifiable result
- Macro rings show logged vs target with correct colors
- Letter grade matches web app for same data
- Weekly view shows heatmap with correct colors
- Gap analysis returns and renders AI text within 5s

---

## Phase 7 — Hydration Tab

**Goal:** Water tracking and sweat output calculation.

### Screen

```
app/(app)/today/hydration.tsx   ← Can also live as a section in Today or its own tab
```

Recommend surfacing this as a dedicated section reachable from the Today tab's QuickRow (tap the water widget → full hydration screen).

### Components

**WaterTracker:**
- Visual cup grid (8 cups = 64oz default target)
- Tap cup to fill/unfill
- Shows oz logged / oz target
- Auto-fills from `daily-summary.water_cups`

**SweatCalculator:**
- Triggered by: "Calculate my sweat loss" button
- Inputs: city (pre-filled from event), event_id (dropdown from today's events)
- `POST /api/nutrition/sweat { athlete_id, event_id, city }` → returns sweat oz + adjusted hydration target
- Result card: "You may lose X oz of sweat — drink Y extra cups"

**HydrationTips:**
- Static science cards (port from web `HydrationScreen.jsx`) — urine color guide, pre-game hydration protocol

### API calls

```
GET  /api/water-log/:id/today
POST /api/water-log/              { athlete_id, cups, date? }
POST /api/nutrition/sweat         { athlete_id, event_id, city }   ← path is /sweat not /sweat-output
```

### Verifiable result
- Cups persisted and match Today tab QuickRow count
- Sweat calculator returns result for an event with a city set
- Hydration target adjusts when sweat output result is received

---

## Phase 8 — Recipes Tab

**Goal:** Recipe browser with category filter, allergen filter, and AI swap.

### Screens

```
app/(app)/library/recipes/
  index.tsx         ← Browse + filter
  [id].tsx          ← Recipe detail
```

Note: Recipes is a sub-section of Library or its own tab. Given 5-tab limit, recommend surfacing it under the Library tab as a "Recipes" category.

### Browse screen

- Category pills: pre-game, post-game, recovery, snack, breakfast, etc. (from `GET /api/recipes/categories`)
- Allergen filter chips (from athlete profile)
- Recipe card: name, macros summary, tags, image (if available)

### Recipe detail screen

- Full macro breakdown
- Ingredients list
- Preparation notes
- Tags
- "Swap this recipe" → `POST /api/recipes/swap` → shows AI alternative inline
- "Add to Meal Plan" → opens date + slot picker → `PUT /api/meal-plans/:id/slot`

### API calls

```
GET  /api/recipes/?category=:cat&avoid_allergens=:list
GET  /api/recipes/categories
GET  /api/recipes/:id
POST /api/recipes/swap  { athlete_id, disliked_recipe, meal_timing_category }
```

### Verifiable result
- All recipes load, category filter works
- Recipe detail shows full nutrition data
- AI swap returns alternative recipe within 5s
- "Add to Meal Plan" flow completes and slot appears in Meal Planner

---

## Phase 9 — Library Tab

**Goal:** Content library with science-backed articles, Alex's Picks, and the knowledge Q&A.

### Screens

```
app/(app)/library/
  index.tsx              ← Article list (categories: iron, gameday, carbs, recovery, calcium, hydration, parents)
  articles/[id].tsx      ← Article detail (Markdown renderer)
```

### Article list

- Category pills at top (filter client-side)
- Article card: title, summary, read time, author, category badge
- "Alex's Picks" section at top (personalized for athlete)

### Article detail

- `react-native-markdown-display` renders `body_markdown`
- Author chip, science source citation, read time
- Pull-to-refresh

### Knowledge Q&A (optional, Phase 9b)

- Chat-style input: "Ask AthFuelPath..."
- `POST /api/knowledge/ask { question, athlete_id }` → returns science-grounded answer. Note: this is POST not GET.
- Rendered in a scrollable chat bubble list

### API calls

```
GET  /api/library/articles?category=:cat&search=:term   ← /articles not /; no athlete_id query param
GET  /api/library/articles/:id                          ← /articles/:id not /:id
GET  /api/library/picks/:id                             ← Alex's personalized weekly picks for athlete
POST /api/knowledge/ask { question, athlete_id }        ← POST not GET
```

### Verifiable result
- Article list loads and category filter narrows results
- Article detail renders markdown with correct formatting (headers, bullets, bold)
- Q&A returns an answer grounded in the knowledge base

---

## Phase 10 — Blueprint Screen

**Goal:** Athlete's personalized nutrition blueprint — all event types, macro targets, science context.

### Screen

```
app/(app)/blueprint/
  index.tsx     ← Full blueprint render
```

Accessible from: Settings → "View Blueprint" or as a dedicated link from the Today BroadcastCard.

### Components

**BlueprintHero:** Athlete name, sport, competition level.

**EventTypeCards:** 5 cards (rest, practice, game, tournament, strength) — each with calorie target, carb/protein/fat ranges, timing notes.

**ScienceCards:** Iron, calcium, magnesium, vitamin D targets with source citations.

**LEA Warning:** Conditional — shown if `_calculated.lea_threshold_kcal` indicates risk.

**Regenerate Blueprint:** Button → `GET /api/athletes/:id/blueprint` (forces regeneration). Loading spinner overlay.

### API calls

```
GET /api/athletes/:id/blueprint
```

### Verifiable result
- Blueprint screen shows all 5 event types with correct macro targets
- Iron/calcium targets match gender-specific rules (girls: 15mg iron, boys: 11mg)
- Regenerate button triggers API call and updates content

---

## Phase 11 — Meal Logging

**Goal:** Athlete can log a meal via photo, text description, or quick-select.

### Screens

```
app/(app)/log-meal/
  index.tsx          ← Method picker (photo / text / quick)
  camera.tsx         ← Camera capture
  describe.tsx       ← Text description form
  quick.tsx          ← Recent meals quick-select
  result.tsx         ← Logged confirmation + macro estimate
```

### Log methods

**Photo:** expo-camera → capture → display preview → confirm → `POST /api/meals/` with `{ log_method: "photo", description: "Photo log [timestamp]", athlete_id }`. (Backend AI parsing via Claude can be added later — for MVP, log method = "photo" with no macros, prompts parent to estimate.)

**Text description:** Free-form text input → `POST /api/nutrition/estimate { athlete_id, description }` first to get Claude's macro estimate, then `POST /api/meals/ { log_method: "text", description, ...macros }` to persist. The `/estimate` endpoint already exists and wraps `claude_ai.py`.

**Quick-select:** Last 10 `meal_logs` for athlete → tap any → re-log it. `POST /api/meals/` with same description/macros.

### API calls

```
GET  /api/meals/athlete/:id                              ← quick-select history
POST /api/nutrition/estimate { athlete_id, description } ← Claude macro estimate (text logging)
POST /api/meals/             { athlete_id, log_method, description, calories?, carbs_g?, protein_g?, fat_g? }
```

### Verifiable result
- Camera opens, captures photo, confirm screen appears
- Confirming logs the meal (appears in Nutrition tab)
- Fuel score on Today tab updates after logging
- Quick-select shows recent meals, tapping re-logs instantly

---

## Phase 12 — Push Notifications

**Goal:** Expo push notifications replace web VAPID push. Meal timing reminders delivered natively.

### Backend change required (one new endpoint)

Add to `api/routes/notifications.py`:

```python
class ExpoPushToken(BaseModel):
    athlete_id: int
    token: str          # ExponentPushToken[...]
    platform: str       # ios | android

@router.post("/expo-token")
def register_expo_token(data: ExpoPushToken):
    # Store in push_subscriptions table with endpoint = data.token, p256dh = "expo", auth = platform
    ...
```

Add a new backend cron or trigger to send via Expo Push API (`https://exp.host/--/api/v2/push/send`) instead of `pywebpush`.

### Mobile setup

```ts
// services/notifications.ts
import * as Notifications from 'expo-notifications';

export async function registerForPushNotifications(athleteId: number) {
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== 'granted') return;
  const token = await Notifications.getExpoPushTokenAsync({ projectId: EXPO_PROJECT_ID });
  await api.post('/notifications/expo-token', { athlete_id: athleteId, token: token.data, platform: Platform.OS });
}
```

### Local notifications (meal timing reminders)

Schedule local notifications for:
- Pre-game meal (3h before event start)
- Pre-game snack (45min before)
- 30-min recovery window (30min after event end)
- Daily water reminder (noon)

Use `Notifications.scheduleNotificationAsync()` with `CalendarTrigger` based on today's event.

### Verifiable result
- App requests notification permission on first launch
- Expo push token registered in backend DB
- Local notification fires at scheduled meal time (test by setting event 2 minutes from now)
- Backend can send via Expo Push API to device (test via cURL to backend trigger endpoint)

---

## Phase 13 — Profile & Settings

**Goal:** Edit athlete profile, notification preferences, sign out, legal documents.

### Screens

```
app/(app)/settings/
  index.tsx            ← Settings hub
  edit-profile.tsx     ← Edit athlete form (PUT /api/athletes/:id)
  notifications.tsx    ← Toggle notification types
  legal/
    [slug].tsx         ← Terms of Service / Privacy Policy
  about.tsx            ← App version, science credits, disclaimer
```

### Settings hub sections

1. **Athlete Profile** — name, age, weight, allergies (tap to edit)
2. **Notifications** — toggle pre-game meal, pre-game snack, recovery, hydration reminders
3. **Add Another Athlete** — routes back to onboarding `profile` step with parent_id pre-filled
4. **Legal** — Terms of Service, Privacy Policy (`GET /api/legal/terms-of-service`, `GET /api/legal/privacy-policy`) — slugs must match what is seeded in the `legal_documents` table
5. **About** — Version, built by Purvi Shah MS RDN, science sources, disclaimer
6. **Sign Out** — Clears secure store, navigates to auth welcome screen

### API calls

```
PUT /api/athletes/:id   { all profile fields }
GET /api/legal/:slug
```

### Verifiable result
- Edit profile: change weight → save → Today tab recalculates calorie target
- Sign out → secure store cleared → Welcome screen, cannot navigate back
- Legal documents render correctly
- Add athlete routes to onboarding, new athlete appears in athlete switcher

---

## Phase 14 — Polish & Production Readiness

**Goal:** Shipping-quality UX. No blank screens on error, smooth loading states, offline graceful degradation.

### Loading states

Every screen that fetches data shows a skeleton (shimmer placeholder matching layout) while loading. Use a `Skeleton` component built with `react-native-reanimated` linear gradient shimmer.

```
Screens with skeletons: Today, Meal Plan week view, Nutrition, Library
```

### Error states

Every TanStack Query call has an `onError` fallback UI: card with "Couldn't load — tap to retry" + retry button that calls `refetch()`.

### Offline detection

`@react-native-community/netinfo` → monitor connection. When offline:
- Show subtle banner: "No connection — showing last data"
- TanStack Query `staleTime: Infinity` serves cached data
- Write operations (log meal, log water) queue to AsyncStorage and flush on reconnect

### Haptics

```
Meal toggle logged: Haptics.impactAsync(ImpactFeedbackStyle.Light)
Water cup tap: Haptics.impactAsync(ImpactFeedbackStyle.Light)
Form submit: Haptics.notificationAsync(NotificationFeedbackType.Success)
Error: Haptics.notificationAsync(NotificationFeedbackType.Error)
```

### Pull-to-refresh

Every primary list and the Today tab support `RefreshControl` with AthFuelPath green spinner.

### EAS Build setup

```json
// eas.json
{
  "build": {
    "development": { "developmentClient": true, "distribution": "internal" },
    "preview": { "distribution": "internal" },
    "production": {}
  }
}
```

- Configure `EXPO_PUBLIC_API_URL` as EAS secret for production builds
- GitHub Actions: on push to `main` → `eas build --platform all --profile preview`

### Verifiable result
- All screens show skeleton → content transition (no blank flash)
- Kill network → app shows stale data + offline banner
- Restore network → data refreshes automatically
- EAS preview build installs on a physical iOS and Android device via TestFlight / internal track

---

## API Changes Required in Backend

Only two changes needed in the existing backend. All other endpoints work as-is.

### 1. Expo push token endpoint (Phase 12)

**File:** `api/routes/notifications.py`

Add:
```python
class ExpoPushToken(BaseModel):
    athlete_id: int
    token: str
    platform: str  # "ios" | "android"

@router.post("/expo-token", status_code=201)
def register_expo_push_token(data: ExpoPushToken):
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO push_subscriptions
               (athlete_id, endpoint, p256dh, auth)
               VALUES (?, ?, 'expo', ?)""",
            (data.athlete_id, data.token, data.platform),
        )
        conn.commit()
        return {"registered": True}
    finally:
        conn.close()
```

### 2. Meal log endpoint accepts `logged_at` from client (minor)

Current `MealLogCreate` model does not accept `logged_at` — it defaults to `CURRENT_TIMESTAMP`. The mobile app needs to pass an ISO timestamp so logs are attributed to the correct local date (timezone awareness).

**File:** `api/models.py`
```python
class MealLogCreate(BaseModel):
    ...
    logged_at: Optional[str] = None  # ISO timestamp from client
```

**File:** `api/routes/meals.py` — use `data.logged_at or "CURRENT_TIMESTAMP"` in the INSERT.

---

## Phase Execution Order & Timeline

| Phase | Scope | Est. Sessions | Gate |
|---|---|---|---|
| 0 | Bootstrap + health check | 1 | App boots, API responds |
| 1 | Auth (login + onboarding) | 2–3 | End-to-end sign up + sign in |
| 2 | Navigation shell | 1 | Tabs navigate, athlete switcher works |
| 3 | Today tab | 2 | Mission items, water, fuel score live |
| 4 | Meal Planner tab | 2–3 | Full week, recipe assignment, AI generate |
| 5 | Schedule tab | 1–2 | Add/delete events, affects Today + Plan |
| 6 | Fuel Report (Nutrition) tab | 2 | Macro rings + weekly summary |
| 7 | Hydration tab | 1 | Cups + sweat calculator |
| 8 | Recipes tab | 1 | Browse, filter, detail, swap |
| 9 | Library tab | 1 | Articles + markdown + Q&A |
| 10 | Blueprint screen | 1 | All event types rendered |
| 11 | Meal logging | 2 | Camera + text + quick-select |
| 12 | Push notifications | 1–2 | Local + remote delivery confirmed |
| 13 | Profile & Settings | 1 | Edit profile, legal, sign out |
| 14 | Polish + EAS Build | 1–2 | TestFlight build installs cleanly |

**Total: ~22–26 Claude Code sessions to production-ready TestFlight build.**

---

## Non-Goals (out of scope for this build)

- Reports/history charts beyond weekly summary (Phase 6 covers the essentials)
- In-app purchase / subscription paywall
- Social features (sharing, leaderboards)
- Apple Watch / WearOS companion
- Offline meal logging queue (Phase 14 covers detection only — full queue is V2)
- Custom recipe creation by user
- Multiple parent accounts per athlete

---

## File Structure (final)

```
fuelup-mobile/
├── app/
│   ├── (auth)/
│   │   ├── _layout.tsx
│   │   ├── index.tsx           # Welcome
│   │   ├── login.tsx           # Email entry
│   │   └── verify.tsx          # OTP verify
│   ├── (onboarding)/
│   │   ├── _layout.tsx
│   │   ├── consent.tsx
│   │   ├── profile.tsx
│   │   ├── review.tsx
│   │   └── success.tsx
│   ├── (app)/
│   │   ├── _layout.tsx         # Tab navigator
│   │   ├── today/
│   │   │   ├── index.tsx
│   │   │   └── hydration.tsx
│   │   ├── meal-plan/
│   │   │   ├── index.tsx
│   │   │   └── [date].tsx
│   │   ├── schedule/
│   │   │   ├── index.tsx
│   │   │   └── add-event.tsx
│   │   ├── nutrition/
│   │   │   ├── index.tsx
│   │   │   └── weekly.tsx
│   │   ├── library/
│   │   │   ├── index.tsx
│   │   │   ├── articles/[id].tsx
│   │   │   └── recipes/
│   │   │       ├── index.tsx
│   │   │       └── [id].tsx
│   │   ├── blueprint/
│   │   │   └── index.tsx
│   │   ├── log-meal/
│   │   │   ├── index.tsx
│   │   │   ├── camera.tsx
│   │   │   ├── describe.tsx
│   │   │   └── quick.tsx
│   │   └── settings/
│   │       ├── index.tsx
│   │       ├── edit-profile.tsx
│   │       ├── notifications.tsx
│   │       └── legal/[slug].tsx
│   └── _layout.tsx             # Root layout + QueryClientProvider + auth guard
├── components/
│   ├── today/
│   │   ├── BroadcastCard.tsx
│   │   ├── DailyMission.tsx
│   │   ├── MissionItem.tsx
│   │   ├── PerformanceForecast.tsx
│   │   ├── QuickRow.tsx
│   │   └── ScienceEdge.tsx
│   ├── nutrition/
│   │   ├── MacroRing.tsx       # SVG circle progress
│   │   ├── TrafficLightCard.tsx
│   │   └── WeekHeatmap.tsx
│   ├── meal-plan/
│   │   ├── WeekStrip.tsx
│   │   ├── DayCard.tsx
│   │   ├── SlotCard.tsx
│   │   └── RecipePicker.tsx
│   ├── shared/
│   │   ├── Skeleton.tsx        # Shimmer loader
│   │   ├── ErrorCard.tsx
│   │   ├── TagChip.tsx
│   │   ├── Header.tsx
│   │   └── AthleteSwitcher.tsx
│   └── ui/
│       ├── Button.tsx
│       ├── TextInput.tsx
│       ├── Picker.tsx
│       └── Card.tsx
├── services/
│   ├── api.ts                  # fetch wrapper, base URL, error handling
│   └── notifications.ts        # Expo push registration + local scheduling
├── store/
│   ├── authStore.ts            # Zustand: parent, athletes, selected athlete
│   └── queryClient.ts          # TanStack Query client config
├── constants/
│   ├── api.ts                  # API_BASE_URL
│   ├── colors.ts               # Brand colors
│   ├── fonts.ts
│   └── eventTypes.ts           # Event type → display label/color/emoji map
├── hooks/
│   ├── useDailySummary.ts      # TanStack query for today endpoint
│   ├── useMealPlan.ts
│   ├── useSchedule.ts
│   └── useNotifications.ts
├── app.json
├── eas.json
├── .env.local                  # EXPO_PUBLIC_API_URL=http://localhost:8000
├── package.json
└── CLAUDE.md                   # Mobile-specific Claude Code instructions
```

---

## CLAUDE.md for Mobile Repo

Add this file to the new mobile repo root so Claude Code has context:

```markdown
# CLAUDE.md — AthFuelPath Mobile (React Native / Expo)

## Dev commands
npx expo start               # Start Metro bundler (scan QR with Expo Go)
npx expo start --ios         # iOS Simulator
npx expo start --android     # Android Emulator
eas build --platform ios --profile preview   # TestFlight build
eas build --platform android --profile preview # Internal track build

## API
Production: https://fuelup-youth.fly.dev
Local dev:  http://localhost:8000 (run uvicorn in the backend repo)
All endpoints use /api/ prefix. No auth tokens — pass parent_id/athlete_id in body/path.

## Auth
Session stored in expo-secure-store keys: "fuelup_parent_id", "fuelup_athlete_id", "fuelup_email"
On app launch: rehydrate from store → call POST /api/parents/login to validate

## Navigation
Expo Router v4. (auth) group → unauthenticated. (app) group → authenticated.
Root _layout.tsx reads authStore and redirects accordingly.

## State
Server state: TanStack Query (queryClient.ts). Invalidate after mutations.
Client state: Zustand (store/authStore.ts).

## Science rules
Same rules as backend CLAUDE.md apply to any copy shown in the app.
Never use Harris-Benedict. Never recommend supplements for under-18.
Always show disclaimer: "AthFuelPath provides food education guidance — not medical nutrition therapy."
```
