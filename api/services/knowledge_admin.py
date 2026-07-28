"""Shared admin gate for the content-management routes that predate the
session-token system: legal.py, knowledge.py, library.py. All three used to
independently default to the literal string "fuelup-admin" whenever
KNOWLEDGE_ADMIN_KEY wasn't set as a Fly secret — a hardcoded fallback baked
into this public source tree, effectively no real protection at all. This
fails closed instead: a missing key rejects every request rather than
silently accepting a guessable default.
"""
import os
from typing import Optional

from fastapi import Header, HTTPException


def require_knowledge_admin_key(x_admin_key: Optional[str] = Header(None)) -> None:
    real_key = os.getenv("KNOWLEDGE_ADMIN_KEY")
    if not real_key:
        raise HTTPException(500, "Admin key is not configured on this server.")
    if x_admin_key != real_key:
        raise HTTPException(403, "Admin key required. Pass X-Admin-Key header.")
