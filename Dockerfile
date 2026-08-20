# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

WORKDIR /app/frontend-coach
COPY frontend-coach/package*.json ./
RUN npm ci
COPY frontend-coach/ ./
RUN npm run build

# ── Stage 2: Python FastAPI backend ───────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt && \
    rm -rf /root/.cache/

COPY . /code
COPY --from=frontend-builder /app/frontend/dist /code/frontend/dist
COPY --from=frontend-builder /app/frontend-coach/dist /code/frontend-coach/dist

# migration/postgres-cloud-run: no more /data SQLite volume — PostgreSQL is
# reached over the network (DATABASE_URL) or a Cloud SQL Unix socket
# (INSTANCE_UNIX_SOCKET), neither of which needs local disk persistence.

EXPOSE 8000

# Cloud Run injects PORT at runtime and expects the container to listen on
# it; Fly.io/local docker run don't set it, so default to 8000. Exec-form
# CMD does NOT expand env vars, so this uses shell + exec (replaces the
# shell process with uvicorn — keeps signal handling or that would break
# graceful shutdown, PID 1 issues, and Cloud Run's SIGTERM handling).
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
