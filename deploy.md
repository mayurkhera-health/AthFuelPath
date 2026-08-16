# AthFuelPath — Fly.io Deployment Guide

## Architecture

Single Fly.io app serving:
- **FastAPI backend** on port 8080 (`uvicorn api.main:app`)
- **React frontend** — built at deploy time, served as static files from `/` via FastAPI
- **SQLite database** — persisted on a Fly.io volume mounted at `/data/fuelup.db`
- **Region**: `sjc` (San Jose, CA — pilot location)

---

## Prerequisites

1. **Install flyctl**
   ```bash
   brew install flyctl
   # or
   curl -L https://fly.io/install.sh | sh
   ```

2. **Create a Fly.io account and log in**
   ```bash
   fly auth login
   ```

---

## First-Time Deployment

### Step 1 — Create the app

```bash
fly launch --no-deploy --name fuelup-youth
```

When prompted:
- **Region**: `sjc` (San Jose)
- **PostgreSQL**: No (we use SQLite)
- **Redis**: No
- Accept the generated `fly.toml` (already configured in this repo)

> If the app name `fuelup-youth` is taken, pick a unique name and update `app =` in `fly.toml`.

### Step 2 — Create the persistent volume for SQLite

```bash
fly volumes create fuelup_data --size 1 --region sjc
```

> The volume is mounted at `/data`. The database lives at `/data/fuelup.db`.
> Only 1 GB is needed for the pilot — resize later with `fly volumes extend`.

### Step 3 — Set secrets

```bash
fly secrets set \
  AWS_REGION="us-east-1" \
  AWS_ACCESS_KEY_ID="AKIA..." \
  AWS_SECRET_ACCESS_KEY="..." \
  BEDROCK_MODEL_ID="mistral.ministral-3-8b-instruct" \
  FDC_API_KEY="your-fdc-key" \
  SECRET_KEY="your-django-secret-key" \
  OPENWEATHERMAP_API_KEY="your-owm-key" \
  VAPID_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----" \
  VAPID_PUBLIC_KEY="BJ5nVY_..." \
  VAPID_CONTACT="mailto:purvi@dietsandlife.com"
```

> Never commit secrets to git. Verify with `fly secrets list`.

### Step 4 — Deploy

```bash
fly deploy
```

This will:
1. Build the React frontend (`npm run build`) inside the Docker multi-stage build
2. Install Python dependencies
3. Start `uvicorn` serving both the API and the compiled frontend

### Step 5 — Initialize the database

Run this once after the first successful deploy:

```bash
fly ssh console -C "python db/setup.py"
```

Expected output: `AthFuelPath database initialized.`

### Step 6 — Verify

```bash
fly open          # Opens the app in your browser
fly logs          # Watch live logs
```

Check the health endpoint: `https://fuelup-youth.fly.dev/health`

---

## Subsequent Deploys

```bash
fly deploy
```

The database volume persists across deploys — no need to re-initialize.

---

## Environment Variables

| Variable | Where set | Notes |
|---|---|---|
| `DB_PATH` | `fly.toml` `[env]` | `/data/fuelup.db` — do not change |
| `PORT` | `fly.toml` `[env]` | `8080` — do not change |
| `AWS_REGION` | `fly secrets` | Bedrock region (e.g. `us-east-1`) |
| `AWS_ACCESS_KEY_ID` | `fly secrets` | IAM user with `bedrock:InvokeModel` |
| `AWS_SECRET_ACCESS_KEY` | `fly secrets` | IAM secret for Bedrock |
| `BEDROCK_MODEL_ID` | `fly secrets` | Default `mistral.ministral-3-8b-instruct` |
| `FDC_API_KEY` | `fly secrets` | USDA FoodData Central |
| `SECRET_KEY` | `fly secrets` | Django secret key |
| `OPENWEATHERMAP_API_KEY` | `fly secrets` | Weather for game-day nutrition |
| `VAPID_PRIVATE_KEY` | `fly secrets` | Web push notifications |
| `VAPID_PUBLIC_KEY` | `fly secrets` | Web push notifications |
| `VAPID_CONTACT` | `fly secrets` | Web push contact email |

---

## Local Development

Start the backend:
```bash
source venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

Start the frontend (in a separate terminal):
```bash
cd frontend
npm install
npm run dev
```

The frontend reads `VITE_API_URL` from `frontend/.env.local` (already configured to `http://localhost:8000`).
In production, `VITE_API_URL` is unset so all `/api/*` calls are relative to the same origin.

---

## Useful Commands

```bash
fly status                          # Machine health and deployment status
fly logs                            # Tail live logs
fly ssh console                     # SSH into the running container
fly ssh console -C "python db/setup.py"   # Re-initialize the database
fly volumes list                    # List volumes
fly volumes extend fuelup_data --size 5   # Grow the volume to 5 GB
fly secrets list                    # List secret names (not values)
fly secrets set KEY=value           # Add or update a secret
fly scale count 1                   # Ensure one machine is running
fly deploy --strategy rolling       # Zero-downtime deploy
```

---

## Scaling

The default config uses one shared-CPU machine with 512 MB RAM. For the pilot this is sufficient.

To scale up:
```bash
# More RAM
fly scale memory 1024

# Dedicated CPU
fly scale vm performance-1x
```

> SQLite with a single machine is appropriate for the pilot phase. If you later need multiple machines, migrate to Fly Postgres (or Turso for distributed SQLite).

---

## Troubleshooting

**App won't start**
```bash
fly logs
```
Check for missing secrets — the most common cause.

**Database errors**
```bash
fly ssh console
ls /data          # Should show fuelup.db after init
```

**Volume not attached**
```bash
fly volumes list
```
Ensure the volume region matches the machine region (`sjc`).

**Frontend 404s on refresh**
FastAPI's `StaticFiles(html=True)` serves `index.html` for unknown paths, enabling React Router navigation. If you see 404s, ensure the build completed successfully with `fly logs`.
