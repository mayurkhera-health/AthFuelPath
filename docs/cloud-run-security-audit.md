# AthFuelPath — Cloud Run Public Exposure: Authentication & Authorization Audit

**Branch:** `migration/postgres-cloud-run`
**Scope:** every endpoint under `api/routes/*.py` (38 files) plus the 3 routes declared directly in `api/main.py`.

## Security Hardening Pass 1 — status

Implemented on this branch, not yet committed. Full backend suite: **1063 passed, 4 failed** (the 4 failures are pre-existing, unrelated to auth — static recipe-content drift and one pure-Python window-template logic bug, both reproduce identically on `main`). 57 new/updated tests added, all passing.

| # | Item | Status |
|---|---|---|
| 1 | `POST /api/athletes` — verify caller owns `data.parent_id` | ✅ FIXED |
| 2 | `POST /api/events/` — verify caller owns `data.athlete_id` | ✅ FIXED |
| 3 | `meals.py` — all 5 endpoints, DELETE resolves ownership via the meal record | ✅ FIXED |
| 4 | `meal_plans.py` — all 5 endpoints | ✅ FIXED |
| 5 | `GET /api/nutrition/targets/{id}`, `GET /api/nutrition/timing/{id}` | ✅ FIXED |
| 6 | `PATCH /api/notifications/fueliq-prefs` | ✅ FIXED |
| 7 | `POST /api/recipes/generate`, `POST /api/recipes/swap` (ownership checked before any AI call) | ✅ FIXED |
| 8 | `POST /api/parents/{parent_id}/confirm` | ✅ FIXED |
| 9 | `DELETE /api/parents/test-reset` | ✅ FIXED — route removed entirely (no test/client depended on HTTP access) |
| 10 | SSRF in `GET /api/events/fetch-ics` | ✅ FIXED — session required; reuses `ics_sync.fetch_ics_text`'s SSRF guard (redirect-safe, IPv4+IPv6). See note below — the guard itself was hardened further during this pass. |
| 11 | `GET /api/knowledge/health` | ✅ FIXED — gated behind `require_knowledge_admin_key` |
| 12 | `hmac.compare_digest` for key/email comparisons | ✅ FIXED — `knowledge_admin.py`, `report_config.py` |
| — | `POST /api/parents/login`, `POST /api/auth/login` (email-only login) | **OUT OF SCOPE for Pass 1 per explicit instruction — unchanged, still open** |
| — | Legacy web-push endpoints in `notifications.py` (`/subscribe`, `/{athlete_id}/prefs` GET+PUT, `/{athlete_id}/unsubscribe`) | **Not touched — deferred pending confirmation of live client usage, per instruction** |
| — | `POST /api/auth/athlete-create-login/{athlete_id}` rate limiting | Not in Pass 1 scope — still outstanding |
| — | `POST /api/support/report`, `POST /api/feedback/feature-request` loose parent/athlete_id trust | Not in Pass 1 scope (low severity, intentionally public forms) — still outstanding |

**A real, additional bug found and fixed while writing the SSRF tests for item 10:** `ics_sync._is_public_host()` resolved literal IP-address hosts via `socket.getaddrinfo()`, which on this dev machine could misclassify RFC1918 literals (`10.0.0.5`, `192.168.1.1`, `172.16.0.1`) as resolvable after other outbound network activity — a real, deterministic reproduction of an OS/resolver-dependent bypass, not a test flake. Fixed by checking IP-literal hosts directly via `ipaddress.ip_address()` first (no network I/O, fully deterministic) and only falling back to DNS resolution for actual hostnames. This strengthens the guard already used by `calendar.py`'s authenticated sync-url route too, not just the newly-protected `fetch-ics` endpoint.

**Read-only audit — no code, schema, or deployment changes made** *(applies to the original audit pass below; Pass 1 above made the code changes described in this status table).*
**Auth mechanisms in this codebase:**
- **`require_session`** (`api/services/session_auth.py`) — HMAC-signed bearer token minted at parent/athlete login. Carries `role` + `parent_id`/`athlete_id`. `assert_owns_athlete()` / `assert_owns_parent()` verify the caller's token actually owns the record in the URL/body (closes BOLA/IDOR).
- **`require_admin`** (`api/services/admin_auth.py`) — single founder password → HMAC bearer token, 24h TTL, IP rate-limited.
- **`require_coach`** (`api/routes/teamcoach_auth.py`) — per-coach password (PBKDF2) → HMAC bearer token, 8h TTL, IP rate-limited. Team-scoped via `assert_coach_owns_team`.
- **`require_knowledge_admin_key`** (`api/services/knowledge_admin.py`) — static `X-Admin-Key` header checked against `KNOWLEDGE_ADMIN_KEY` env var. Fails closed if unset. Gates `legal.py`/`knowledge.py`/`library.py` content-management routes (these predate the session-token system).

**Overall finding:** the newer, session-token-era code (`today.py`, `events.py`'s mutations, `calendar.py`, `fueliq*.py`, `shopping.py`, `plate.py`, `recipes.py`'s selection endpoints, `water.py`, `meal_plan_selections.py`, admin/TeamCoach routes) is consistently and correctly protected — `require_session` + `assert_owns_athlete`/`assert_owns_parent` on every mutating and most reading endpoints. The gaps below cluster almost entirely in **older code that was never retrofitted** when session tokens were introduced: `meals.py` and `meal_plans.py` have **zero auth on every endpoint**, and several individual endpoints elsewhere (`create_athlete`, `create_event`, nutrition targets, a handful of legacy push-notification routes) were missed. There is also one SSRF-class bug (`fetch-ics`) and the flagship issue explicitly called out in the brief: **both login endpoints are email-only**, no password, no OTP, no possession proof.

---

## Endpoint-by-endpoint tables

Legend for column 8 (Security classification): 🟢 SAFE PUBLIC · 🔵 AUTHENTICATED (correctly gated) · 🟡 NEEDS REVIEW · 🔴 SECURITY GAP

### `api/main.py` (no prefix)

| Method | Path | Purpose | Auth mechanism | require_session/admin/coach? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| GET | `/api/info` | Static app metadata | None | No | N/A | Yes | 🟢 | None |
| GET | `/health` | Liveness probe | None | No | N/A | Yes | 🟢 | None |
| GET | `/ready` | Readiness probe (DB connectivity + migration version) | None | No | N/A | Yes | 🟢 | None — response never includes connection strings/credentials |

### `api/routes/parents.py` (prefix `/api/parents`)

| Method | Path | Purpose | Auth | Session/admin/coach? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/` | Create parent account | None | No | N/A (creates own record) | **Yes** — signup must be open | 🟢 | None |
| POST | `/{parent_id}/confirm` | Mark a parent's consent confirmed | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_parent`) | No | 🔵 | None — fixed |
| POST | `/login` | **Email-only login** — returns full parent + all athlete records + session token | None | No | N/A | Partially — login must be reachable, but **not with zero proof of possession** | 🔴 | See Critical Issue #1 — **explicitly out of scope for Pass 1, unchanged** |
| POST | `/request-otp` | Request a 6-digit email OTP | None | No | N/A | Yes | 🟢 | None — correctly rate-limited (60s) |
| POST | `/verify-otp` | Verify OTP, return parent+athletes (no session token minted here — see note) | None | No | N/A | Yes | 🟢 | None |
| DELETE | `/test-reset` | ~~Debug endpoint — wiped all data for `test@gmail.com`~~ | — | — | — | — | ✅ | **Removed entirely in Pass 1** — no test or app code depended on HTTP access (only documented as a dev tool in mobile's CLAUDE.md, no call site) |
| DELETE | `/{parent_id}` | Record account-deletion request | `require_session` | Yes | Yes (`assert_owns_parent`) | No | 🔵 | None |
| PATCH | `/{parent_id}/dismiss-schedule-reminder` | Dismiss a reminder card | `require_session` | Yes | Yes | No | 🔵 | None (unrelated pre-existing bug: column doesn't exist — not a security issue) |
| GET | `/exists` | Does an email already have an account? | None | No | N/A | **Yes** — used by signup flow to pre-check | 🟢 | Minor: email-enumeration by design: acceptable for a signup gate |
| PATCH | `/{parent_id}/profile` | Update name/phone | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/{parent_id}` | Fetch parent record | `require_session` | Yes | Yes | No | 🔵 | None |
| POST | `/{parent_id}/blueprint-viewed` | Stamp first-view + fire founder email | `require_session` | Yes | Yes | No | 🔵 | None |

### `api/routes/athletes.py` (prefix `/api/athletes`)

| Method | Path | Purpose | Auth | Session/admin/coach? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/` | **Create athlete** under `data.parent_id` | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_parent(identity, data.parent_id)`) | No — this is the "add another athlete" flow for an already-logged-in parent | 🔵 | None — fixed |
| GET | `/{athlete_id}` | Fetch athlete | `require_session` | Yes | Yes | No | 🔵 | None |
| PUT | `/{athlete_id}` | Update athlete profile | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/{athlete_id}/blueprint` | Get/lazily generate blueprint | `require_session` | Yes | Yes | No | 🔵 | None |
| POST | `/{athlete_id}/regenerate-blueprint` | Re-trigger blueprint generation | `require_session` | Yes | Yes | No | 🔵 | None |
| PATCH | `/{athlete_id}/dismiss-schedule-reminder` | Dismiss reminder | `require_session` | Yes | Yes | No | 🔵 | None |

### `api/routes/onboarding.py` (prefix `/api/onboarding`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/complete` | Create parent + athlete atomically | None | No | N/A (creates own records) | **Yes** — this is the primary signup path | 🟢 | None — do not add auth here |

### `api/routes/auth.py` (prefix `/api/auth`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/login` | **Unified email-only login** (parent or athlete) | None | No | N/A | Partially — same issue as `/api/parents/login` | 🔴 | See Critical Issue #1 |
| POST | `/athlete-create-login/{athlete_id}` | First-time athlete login creation (athlete-claim flow) | None, but gated by requiring a matching `parent_email` + DB-verified `athlete_id ↔ parent_id` link | No | **Yes, at the DB level** (checks athlete belongs to the parent identified by email) | Yes — chicken-and-egg, athlete has no credential yet | 🟡 | See Medium Issue — add rate limiting to match the OTP flow's protection |

### `api/routes/events.py` (prefix `/api/events`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| GET | `/fetch-ics` | Server-side fetch of a client-supplied ICS URL | `require_session` ✅ Pass 1 | Yes | N/A (no target athlete/parent record — just needs a real caller) | No | 🔵 | None — fixed. Delegates to `ics_sync.fetch_ics_text`'s SSRF guard (scheme allowlist, redirect-safe host re-validation on every hop, IPv4+IPv6, rejects loopback/private/link-local/reserved/multicast/unspecified incl. the metadata IP) |
| POST | `/` | Create event under `data.athlete_id` | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_athlete`) | No | 🔵 | None — fixed |
| PUT | `/{event_id}` | Update event | `require_session` | Yes | Yes | No | 🔵 | None |
| PATCH | `/{event_id}/activity-type` | Tag activity type | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/athlete/{athlete_id}` | List an athlete's events | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/{event_id}` | Get one event | `require_session` | Yes | Yes | No | 🔵 | None |
| DELETE | `/{event_id}` | Delete event | `require_session` | Yes | Yes | No | 🔵 | None |

### `api/routes/calendar.py` (prefix `/api/athletes`, mounted as `/{athlete_id}/calendar/...`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/{athlete_id}/calendar/sync-url` | Save + validate BYGA/PlayMetrics feed URL | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/{athlete_id}/calendar/sync-status` | Per-platform connection state | `require_session` | Yes | Yes | No | 🔵 | None |
| DELETE | `/{athlete_id}/calendar/sync-url` | Disconnect a feed | `require_session` | Yes | Yes | No | 🔵 | None — this whole file is a model implementation |

### `api/routes/notifications.py` (prefix `/api/notifications`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/expo-token` | Register push token for athlete/parent | `require_session` | Yes | Yes (with an explicit comment explaining why) | No | 🔵 | None |
| PATCH | `/fueliq-prefs` | Update Fuel IQ notif prefs for `data.athlete_id` | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_athlete`) | No | 🔵 | None — fixed |
| PATCH | `/prefs` | Update Training/Game/Quiet-hours prefs | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/vapid-public-key` | Return the public VAPID key | None | No | N/A | **Yes** — public keys are meant to be public | 🟢 | None |
| POST | `/subscribe` | Web-push subscribe for `data.athlete_id` | **None** | No | **No** | No — appears to be legacy, superseded by `/expo-token` | 🔴 | **Deferred, per explicit Pass 1 instruction** — confirm still used by mobile/web before touching |
| GET | `/{athlete_id}/prefs` | Read legacy push prefs | **None** | No | **No** | No | 🔴 | Same as above — deferred |
| PUT | `/{athlete_id}/prefs` | Write legacy push prefs | **None** | No | **No** | No | 🔴 | Same as above — deferred |
| DELETE | `/{athlete_id}/unsubscribe` | Delete legacy push subscription | **None** | No | **No** | No | 🔴 | Same as above — deferred |

### `api/routes/nutrition.py` (prefix `/api/nutrition`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| GET | `/targets/{athlete_id}` | Compute + **upsert** daily nutrition targets | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_athlete`) | No | 🔵 | None — fixed |
| POST | `/sweat` | Sweat-rate calculation | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/timing/{athlete_id}` | Meal-timing protocol | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_athlete`) | No | 🔵 | None — fixed |

### `api/routes/fueliq.py` + `api/routes/fueliq_daily_challenge.py` (prefix `/api/athletes`)

All 8 endpoints (`hub`, `lessons`, `lessons/{id}`, `lessons/{id}/complete`, `questions/{id}/answer`, `badges`, `daily-challenge`, `daily-challenge/verdict`) use `require_session` + `assert_owns_athlete`. 🔵 None need action.

### `api/routes/recipes.py` (prefix `/api/recipes`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| GET | `/` | List/filter recipe catalog | None | No | N/A | Yes — generic content | 🟢 | None |
| GET | `/categories` | List recipe categories | None | No | N/A | Yes | 🟢 | None |
| POST | `/generate` | AI-generate a recipe using `req.athlete_id`'s allergies | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_athlete`, checked before the AI call) | No | 🔵 | None — fixed |
| GET | `/for-window` | Valid recipes for a window | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/selections/week` | Weekly recipe selections | `require_session` | Yes | Yes | No | 🔵 | None |
| POST | `/selections` | Create a selection | `require_session` | Yes | Yes | No | 🔵 | None |
| DELETE | `/selections/{id}` | Delete a selection | `require_session` | Yes | Yes | No | 🔵 | None |
| POST | `/selections/sync-grocery-list` | Rebuild grocery list from selections | `require_session` | Yes | Yes | No | 🔵 | None |
| GET | `/grocery-list` | Read grocery list | `require_session` | Yes | Yes | No | 🔵 | None |
| PATCH | `/grocery-list/items/{id}` | Toggle checked | `require_session` | Yes | Yes (via join lookup) | No | 🔵 | None |
| GET | `/{recipe_id}` | Get one recipe (generic catalog) | None | No | N/A | Yes | 🟢 | None |
| POST | `/swap` | AI picky-eater swap using `req.athlete_id`'s allergies | `require_session` ✅ Pass 1 | Yes | Yes (`assert_owns_athlete`, checked before the AI call) | No | 🔵 | None — fixed |

### `api/routes/meals.py` (prefix `/api/meals`) — ✅ Pass 1: all 5 endpoints now protected

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/analyze-photo` | AI photo → nutrition analysis for `data.athlete_id` | `require_session` | Yes | Yes (`assert_owns_athlete`, checked before the AI call) | No | 🔵 | None — fixed |
| POST | `/analyze-voice` | AI voice → nutrition analysis | `require_session` | Yes | Yes (checked before the AI call) | No | 🔵 | None — fixed |
| POST | `/` | Log a meal for `data.athlete_id` | `require_session` | Yes | Yes | No | 🔵 | None — fixed |
| GET | `/athlete/{athlete_id}` | Read meal history (food, macros) | `require_session` | Yes | Yes | No | 🔵 | None — fixed |
| DELETE | `/{meal_id}` | Delete a meal log — request carries only `meal_id` | `require_session` | Yes | Yes — `athlete_id` resolved from the meal row itself first, then checked | No | 🔵 | None — fixed |

### `api/routes/meal_plans.py` (prefix `/api/meal-plans`) — ✅ Pass 1: all 5 endpoints now protected

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| GET | `/{athlete_id}` | Read weekly meal plan | `require_session` | Yes | Yes | No | 🔵 | None — fixed |
| PUT | `/{athlete_id}/slot` | Assign a recipe to a slot | `require_session` | Yes | Yes | No | 🔵 | None — fixed |
| DELETE | `/{athlete_id}/slot` | Clear a slot | `require_session` | Yes | Yes | No | 🔵 | None — fixed |
| POST | `/{athlete_id}/log-slot` | Log a planned meal as eaten | `require_session` | Yes | Yes | No | 🔵 | None — fixed |
| POST | `/generate` | AI-generate a full weekly plan for `data.athlete_id` | `require_session` | Yes | Yes (checked before the AI call) | No | 🔵 | None — fixed |

### `api/routes/meal_plan_selections.py` (prefix `/api/meal-plan`)

Both endpoints (`POST /windows/{key}/items`, `DELETE /windows/{key}/items/{id}`) use `require_session` + `assert_owns_athlete`. 🔵 None need action. (Notably the newest-looking file in this cluster — built correctly from day one.)

### `api/routes/plate.py` (prefix `/api/plate`)

`GET /window` uses `require_session` + `assert_owns_athlete`. 🔵 None needed.

### `api/routes/shopping.py`, `instacart.py`, `instacart_feedback.py`, `water.py` (prefixes `/api/shopping`, `/api/instacart`, `/api/water-log`)

Every endpoint across all four files uses `require_session` + `assert_owns_athlete` (or a conditional check when `athlete_id` is optional, in `instacart_feedback.py`). 🔵 None need action.

### `api/routes/coach.py` (prefix `/api/coach`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/feedback` | Anonymous thumbs up/down telemetry, no athlete_id | None | No | N/A — no target record | Yes | 🟢 | None |
| POST | `/dietitian-booking` | Book a dietitian session for `body.athlete_id` | `require_session` | Yes | Yes | No | 🔵 | None |

### `api/routes/support.py`, `api/routes/feedback.py` (prefixes `/api/support`, `/api/feedback`)

| Method | Path | Purpose | Auth | Session? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| POST | `/api/support/report` | Submit a problem report (optional `parent_id`) | None | No | No — `parent_id` used only to resolve an email for internal notification, never returned to caller | Yes — must work even from a broken/logged-out session | 🟡 | Low severity: worst case is an unwanted confirmation email to a guessed parent_id. Acceptable to leave public; note only. |
| POST | `/api/feedback/feature-request` | Submit a feature suggestion (optional `athlete_id`) | None | No | Same pattern as above | Yes | 🟡 | Same low-severity note |

### `api/routes/today.py` (prefix `/api/athletes`)

All 7 endpoints (`meal-plan`, `today`, `dismiss-wind-down`, `windows/{slot}/capture` POST+DELETE, `daily-summary`, `weekly-summary`) use `require_session` + `assert_owns_athlete`. 🔵 None need action.

### `api/routes/library.py` (prefix `/api/library`)

| Method | Path | Purpose | Auth | Session/admin? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| GET | `/articles` | List published articles | None | No | N/A | Yes — generic content | 🟢 | None |
| GET | `/picks/{athlete_id}` | This week's personalized picks | `require_session` | Yes | Yes (explicit comment re: why session, not query param) | No | 🔵 | None |
| GET | `/articles/{id}` | Read one article | None | No | N/A | Yes | 🟢 | None |
| POST/PUT | `/articles`, `/articles/{id}` | Create/edit articles | `X-Admin-Key` | Admin (knowledge key) | N/A | No | 🔵 | None |
| POST | `/picks/{athlete_id}/generate` | Force-regenerate picks | `X-Admin-Key` | Admin | N/A | No | 🔵 | None |
| POST | `/admin/articles/{id}/publish`, `/unpublish` | Toggle visibility | `X-Admin-Key` | Admin | N/A | No | 🔵 | None |
| GET | `/admin/articles` | List all articles incl. drafts | `X-Admin-Key` | Admin | N/A | No | 🔵 | None |

### `api/routes/knowledge.py` (prefix `/api/knowledge`)

| Method | Path | Purpose | Auth | Session/admin? | Ownership validated? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|---|
| GET | `/` | List all knowledge items | `X-Admin-Key` | Admin | N/A | No | 🔵 | None |
| POST | `/ingest` | Trigger re-ingestion | `X-Admin-Key` | Admin | N/A | No | 🔵 | None |
| GET | `/sources` | List approved sources | None | No | N/A | Yes | 🟢 | None |
| GET | `/health` | Bedrock config + chunk-count diagnostics | `X-Admin-Key` ✅ Pass 1 | Admin | N/A | No | 🔵 | None — fixed, now gated behind `require_knowledge_admin_key` like this file's other management routes |
| POST | `/ask` | Nutrition Coach Q&A | `require_session` | Yes | Yes | No | 🔵 | None |
| GET/PATCH/DELETE | `/{slug}`, `/{slug}/status` | Manage a knowledge item | `X-Admin-Key` | Admin | N/A | No | 🔵 | None |

### `api/routes/legal.py` (prefix `/api/legal`)

| Method | Path | Purpose | Auth | Session/admin? | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|---|
| GET | `/`, `/{slug}` | Privacy Policy / ToS / disclaimers | None | No | **Yes — App Store requires these be accessible without login** | 🟢 | None |
| PUT | `/{slug}` | Edit a legal document | `X-Admin-Key` | Admin | No | 🔵 | None |

### `api/routes/fuel_report.py`, `report_config.py`, `reports.py`, `analysis.py`

All athlete-scoped endpoints use `require_session` + `assert_owns_athlete`. `report_config.py`'s `GET`/`PUT ""` additionally layer a hardcoded-founder-email check on top of `require_session` (defense in depth). 🔵 None need action. The email comparison now uses `hmac.compare_digest` (✅ Pass 1 item 12) instead of `!=`.

### `api/routes/teamcoach_auth.py` (prefix `/api/team-coach/auth`)

| Method | Path | Purpose | Auth | Intentionally public? | Class | Recommended action |
|---|---|---|---|---|---|---|
| POST | `/login` | Coach password login | None (rate-limited) | Yes | 🟢 | None |
| GET | `/me` | Coach's own profile | `require_coach` | No | 🔵 | None |

### `api/routes/teamcoach_admin.py` (prefix `/api/admin/team-coach`)

All 5 endpoints (`create_coach`, `create_team`, `grant_coach_access`, `add_to_roster`, `trigger_snapshot`) use `Depends(require_admin)`. 🔵 None need action.

### `api/routes/teamcoach_dashboard.py` (prefix `/api/team-coach/teams`)

All 4 endpoints use `require_coach` + `assert_coach_owns_team`. 🔵 None need action.

### `api/routes/admin.py`, `admin_analytics.py`, `admin_health.py`, `admin_overview.py`, `admin_action_hub.py` (prefix `/api/admin`)

`POST /login` is public by necessity (rate-limited, fails closed if `ADMIN_PASSWORD` unset). Every other endpoint across all 5 files — including the destructive `DELETE /athletes/{id}` and `DELETE /parents/{id}` (which requires typing `"DELETE"` to confirm and writes an audit-log row) — uses `Depends(require_admin)`. 🔵 None need action. This is the most consistently well-secured cluster in the codebase.

---

## A. Critical issues — must fix before Cloud Run becomes public

*(Original findings preserved below; each now carries its Pass 1 status.)*

1. **Email-only login = full account takeover** (`POST /api/parents/login`, `POST /api/auth/login`). Given only a registered email address — no password, no OTP — either endpoint returns the full parent record, every linked athlete's full profile (allergies, DOB, weight, schedule, etc.), and mints a 30-day session bearer token. A proper OTP flow (`request-otp` / `verify-otp`) already exists in parallel and is unused by these two endpoints. On Fly.io with a small, trusted tester population this was low-risk; on public Cloud Run, anyone who knows or can guess a parent's email owns that family's account outright. **This is the single highest-priority fix.** — **⚠️ OUTSTANDING.** Explicitly out of scope for Pass 1 per instruction; unchanged. Must be resolved before any public traffic cutover.

2. **`POST /api/athletes` never verifies the caller owns `data.parent_id`.** Zero auth of any kind — only checks that the target parent has `consent_confirmed = TRUE`. Anyone can create arbitrary athlete profiles attached to any real parent account. Directly the question the brief asked to evaluate — confirmed: **it does not**, and needs `require_session` + `assert_owns_parent(identity, data.parent_id)`. — **✅ FIXED in Pass 1.**

3. **SSRF in `GET /api/events/fetch-ics`.** The server fetches any client-supplied URL with no allowlist and no private/link-local IP filtering. On Cloud Run this can reach the GCP metadata server (`169.254.169.254`) and internal-only services. Needs both an IP-range block (reject RFC 1918, link-local, and metadata ranges after DNS resolution) and `require_session`. — **✅ FIXED in Pass 1.** Session required; delegates to the existing `ics_sync.fetch_ics_text` SSRF guard, which was itself hardened during this pass (see Pass 1 status table above — IP-literal hosts are now checked deterministically via `ipaddress` instead of relying solely on `socket.getaddrinfo`).

4. **`DELETE /api/parents/test-reset` is a live debug endpoint with no authentication**, gated only by a hardcoded string comparison (`email == "test@gmail.com"`). Narrow blast radius today, but any test/debug endpoint reachable with no credential must not ship to a publicly-reachable Cloud Run service. Remove entirely, or gate behind `require_admin` **and** an environment flag that's off in production. — **✅ FIXED in Pass 1.** Route removed entirely.

5. **`meals.py` — every one of its 5 endpoints has zero authentication.** This is the most severe single file: unauthenticated reads of eating-history data (`GET /athlete/{id}`), unauthenticated writes that inject fabricated meal-log entries into any account (`POST /`), an unauthenticated delete with **no ownership check of any kind — not even a matching athlete_id** (`DELETE /{meal_id}`), and two AI-backed analysis endpoints (`analyze-photo`, `analyze-voice`) that are wide open to unmetered cost-abuse. — **✅ FIXED in Pass 1.** All 5 endpoints protected; `DELETE` resolves `athlete_id` from the meal row before checking ownership.

6. **`meal_plans.py` — every one of its 5 endpoints has zero authentication.** Same severity class as `meals.py`: unauthenticated read/write/delete of an athlete's weekly meal plan for any `athlete_id`, plus an AI-backed `POST /generate` open to cost abuse. — **✅ FIXED in Pass 1.**

7. **`GET /api/nutrition/targets/{athlete_id}` has zero authentication and both reads and writes** (it upserts `daily_targets` on every call) for any athlete_id. — **✅ FIXED in Pass 1.**

## B. Medium-priority issues

1. **`POST /api/auth/athlete-create-login/{athlete_id}`** is legitimately public (an athlete has no credential yet), and does correctly verify the target athlete belongs to the parent identified by `parent_email` — but has no rate limiting, unlike the OTP flow. Recommend adding the same rate-limit pattern used elsewhere in the codebase. — **⚠️ OUTSTANDING.** Not in Pass 1 scope.
2. **Legacy web-push endpoints in `notifications.py`** (`POST /subscribe`, `GET`/`PUT /{athlete_id}/prefs`, `DELETE /{athlete_id}/unsubscribe`) have zero auth and appear superseded by the properly-protected `/expo-token` flow. Confirm with the mobile/web clients whether these are still called; if not, delete them — if so, add `require_session` + `assert_owns_athlete`. — **⚠️ OUTSTANDING — deliberately deferred.** Explicit Pass 1 instruction: do not touch until live usage is confirmed separately.
3. **`PATCH /api/notifications/fueliq-prefs`** — no auth, low-sensitivity data but still a BOLA write. — **✅ FIXED in Pass 1.**
4. **`GET /api/nutrition/timing/{athlete_id}`** — no auth, read-only, moderate sensitivity (meal-timing tied to schedule). — **✅ FIXED in Pass 1.**
5. **`POST /api/recipes/generate`, `POST /api/recipes/swap`** — no auth; unauthenticated AI-cost-abuse vector plus minor allergy-derived inference. Both should require `require_session` + `assert_owns_athlete`. — **✅ FIXED in Pass 1.** Ownership verified before the AI call in both.
6. **`GET /api/knowledge/health`** — no auth; leaks Bedrock configuration status and chunk counts. Minor reconnaissance value for an attacker; consider gating. — **✅ FIXED in Pass 1.** Gated behind `require_knowledge_admin_key`.
7. **`POST /api/support/report`, `POST /api/feedback/feature-request`** — intentionally public forms; both accept an optional `parent_id`/`athlete_id` used only server-side to resolve a notification email, never echoed back to the caller. Worst case is an unwanted email to a guessed ID. Low severity — flagging for awareness, not urgent. — **⚠️ OUTSTANDING.** Not in Pass 1 scope (low severity, intentionally public).
8. **`POST /api/parents/{parent_id}/confirm`** — no auth, unauthenticated state mutation on an arbitrary parent_id. Low practical impact (only flips a boolean the account holder benefits from), but should either be removed (given `create_parent` already sets `consent_confirmed` inline from the signup payload) or gated. — **✅ FIXED in Pass 1.** Gated (kept, not removed — still reachable for whatever legacy flow calls it, now ownership-checked).
9. **Non-constant-time string comparisons** for `X-Admin-Key` (`knowledge_admin.py`) and the founder-email check (`report_config.py`) use `!=` instead of `hmac.compare_digest`. Theoretical timing-attack surface only; the real security boundary in both cases is a separate, non-guessable secret. Low priority, cheap to fix. — **✅ FIXED in Pass 1.**

## C. Routes intentionally safe to remain public

- `GET /api/info`, `GET /health`, `GET /ready`
- `POST /api/parents/` (create_parent), `POST /api/onboarding/complete` — the two account-creation entry points
- `GET /api/parents/exists` — email-existence check for the signup flow (accepted minor enumeration)
- `POST /api/parents/request-otp`, `POST /api/parents/verify-otp` — the real login mechanism
- `GET /api/recipes/`, `/categories`, `/{recipe_id}` — generic recipe catalog, no athlete data
- `GET /api/library/articles`, `/articles/{id}` — generic published content
- `GET /api/legal/`, `/{slug}` — Privacy Policy / ToS / disclaimers (App Store requirement)
- `GET /api/notifications/vapid-public-key` — public key by design
- `POST /api/coach/feedback` — anonymous telemetry, no target record
- `GET /api/knowledge/sources` — static list of approved sources
- `POST /api/admin/login`, `POST /api/team-coach/auth/login` — rate-limited, fail closed if secrets unset

## D. Minimal remediation plan

Ordered by severity, smallest correct change per item — no redesign, no new auth mechanism (the codebase's existing `require_session`/`assert_owns_athlete`/`assert_owns_parent` pattern already covers every gap below):

1. **Retire (or gate) the two email-only login endpoints.** Either remove `POST /api/parents/login` and `POST /api/auth/login`'s parent-branch entirely in favor of the existing OTP flow, or require a verified OTP code in the same request before minting a session token. This is the one item that may need a product/mobile-client conversation (mobile currently calls these routes) before it can ship — flag for explicit sign-off. — **⚠️ STILL OUTSTANDING.** The one remaining blocker before public Cloud Run traffic.
2. ~~Add `require_session` + `assert_owns_parent(identity, data.parent_id)` to `POST /api/athletes`.~~ — **✅ DONE (Pass 1).**
3. ~~Add `require_session` + `assert_owns_athlete` to: `POST /api/events/`, all 5 endpoints in `meals.py`, all 5 endpoints in `meal_plans.py`, nutrition targets/timing, recipes generate/swap, fueliq-prefs.~~ — **✅ DONE (Pass 1).**
4. ~~Remove or hard-gate `DELETE /api/parents/test-reset`.~~ — **✅ DONE (Pass 1).** Removed entirely.
5. ~~Fix the SSRF in `GET /api/events/fetch-ics`.~~ — **✅ DONE (Pass 1).**
6. **Decide the fate of the 4 legacy push-notification endpoints in `notifications.py`** — confirm whether mobile/web still call them; delete if dead, add ownership checks if live. — **⚠️ STILL OUTSTANDING**, deliberately deferred per Pass 1 instructions. (`POST /api/parents/{parent_id}/confirm` was resolved — kept and gated, not removed.)
7. ~~Low priority: switch the two `!=` admin-key/email comparisons to `hmac.compare_digest`; gate `GET /api/knowledge/health`.~~ — **✅ DONE (Pass 1).**

Only item 1 (email-only login) and item 6 (legacy push endpoints) remain before this branch is ready for a public Cloud Run traffic cutover.

## E. Security Hardening Pass 1 — implementation record

**Files changed:**
- `api/routes/athletes.py`, `events.py`, `meals.py`, `meal_plans.py`, `nutrition.py`, `notifications.py`, `recipes.py`, `parents.py`, `knowledge.py`, `report_config.py` — auth/ownership checks added; `parents.py`'s `test-reset` route removed.
- `api/services/ics_sync.py` — added `is_unspecified` to the SSRF guard's rejected-IP list; hardened `_is_public_host` to check IP-literal hosts via `ipaddress` directly instead of only via `socket.getaddrinfo` (see Pass 1 status table above for why).
- `api/services/knowledge_admin.py` — `hmac.compare_digest` for the admin-key comparison.
- 22 test files updated (mostly adding `headers=auth_headers(...)` to `POST /api/athletes/` / `POST /api/events/` call sites that the new auth requirement broke) + 7 new test files (`test_meals_bola.py`, `test_meal_plans_bola.py`, `test_athlete_and_event_create_bola.py`, `test_nutrition_targets_timing_bola.py`, `test_fueliq_prefs_and_recipes_ai_bola.py`, `test_parents_confirm_bola.py`, `test_fetch_ics_route_ssrf.py`).

**Test results:** full backend suite, 1063 passed / 4 failed. The 4 failures are pre-existing and unrelated to authentication (static `recipes.json` content drift in `test_recipe_generator.py`, one pure-Python logic bug in `test_window_templates.py` — both reproduce identically on `main`, confirmed during the earlier PostgreSQL migration work on this same branch).

**Not touched, per explicit Pass 1 scope:** `POST /api/parents/login`, `POST /api/auth/login` (both unchanged, still open); the 4 legacy web-push endpoints in `notifications.py`; database schema; Fly.io configuration; the mobile repository; `main`.
