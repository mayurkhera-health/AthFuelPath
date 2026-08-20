"""
Admin System Health endpoints (all behind require_admin):
  GET  /api/admin/health                    — all checks + overall status
  GET  /api/admin/health/incidents          — transition history, newest first
                                              (?check_name= filters to one sensor)
  GET  /api/admin/health/checks/{name}      — drill-down: check row, threshold,
                                              incident history, sensor evidence
  POST /api/admin/health/run                — run the 15-min suite on demand
                                              (?check_name= re-runs just one);
                                              1/min floor, per-check for singles
"""

import time

from fastapi import APIRouter, Depends, HTTPException

from api.database import get_conn
from api.services import health_service
from api.services.admin_auth import require_admin

router = APIRouter()

_RUN_FLOOR_SECONDS = 60
_last_run = {"t": 0.0}
_last_single_run: dict[str, float] = {}


@router.get("/health")
def health(_: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        return health_service.get_health_snapshot(conn)
    finally:
        conn.close()


@router.get("/health/incidents")
def incidents(limit: int = 50, check_name: str | None = None, _: bool = Depends(require_admin)):
    limit = max(1, min(200, limit))
    conn = get_conn()
    try:
        if check_name:
            rows = conn.execute(
                "SELECT * FROM health_incidents WHERE check_name = %s ORDER BY id DESC LIMIT %s",
                (check_name, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM health_incidents ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/health/checks/{check_name}")
def check_detail(check_name: str, _: bool = Depends(require_admin)):
    conn = get_conn()
    try:
        detail = health_service.get_check_detail(check_name, conn)
        if detail is None:
            raise HTTPException(404, "Unknown health check.")
        return detail
    finally:
        conn.close()


@router.post("/health/run")
def run_now(check_name: str | None = None, _: bool = Depends(require_admin)):
    now = time.monotonic()
    if check_name:
        if check_name not in health_service.ALL_CHECKS:
            raise HTTPException(404, "Unknown health check.")
        if now - _last_single_run.get(check_name, 0.0) < _RUN_FLOOR_SECONDS:
            raise HTTPException(429, "This check was just run — try again in a moment.")
        _last_single_run[check_name] = now
        health_service.run_single_check(check_name)
    else:
        if now - _last_run["t"] < _RUN_FLOOR_SECONDS:
            raise HTTPException(429, "Health check was just run — try again in a moment.")
        _last_run["t"] = now
        health_service.run_health_tick()
    conn = get_conn()
    try:
        return health_service.get_health_snapshot(conn)
    finally:
        conn.close()
