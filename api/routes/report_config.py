from fastapi import APIRouter, Depends, HTTPException
from api.database import get_conn
from api.services.session_auth import require_session

router = APIRouter()

# Mirrors the client-side gate in app/(app)/settings/index.tsx
# ("isAdmin = isParent && parent?.email === ..."). This is a real session
# token, not a static key shipped in the mobile bundle — anything baked into
# a shipped app binary is extractable, so tying admin access to the same
# login already gating the Settings entry point is the correct mechanism.
_ADMIN_EMAIL = "mkhera@zedventures.com"


def _require_admin(identity, conn):
    if identity.role != "parent":
        raise HTTPException(403, "Admin access required.")
    row = conn.execute("SELECT email FROM parents WHERE id = ?", (identity.parent_id,)).fetchone()
    if not row or dict(row)["email"].strip().lower() != _ADMIN_EMAIL:
        raise HTTPException(403, "Admin access required.")


@router.get("")
def get_report_config(identity=Depends(require_session)):
    """Return all tunable thresholds from report_config table."""
    conn = get_conn()
    try:
        _require_admin(identity, conn)
        rows = conn.execute(
            "SELECT key, value, description, updated_at FROM report_config ORDER BY key"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.put("")
def update_report_config(body: dict, identity=Depends(require_session)):
    """
    Update one or more report_config thresholds.
    Body: { key: new_value, ... }
    Only keys that already exist in the table are updated — unknown keys are ignored.
    """
    if not body:
        raise HTTPException(400, "Request body must contain at least one key-value pair")

    conn = get_conn()
    try:
        _require_admin(identity, conn)
        valid_keys = {
            r["key"]
            for r in conn.execute("SELECT key FROM report_config").fetchall()
        }
        updated = []
        for key, value in body.items():
            if key not in valid_keys:
                continue
            try:
                float_val = float(value)
            except (TypeError, ValueError):
                raise HTTPException(400, f"Value for '{key}' must be numeric")
            conn.execute(
                "UPDATE report_config SET value = ?, updated_at = datetime('now') WHERE key = ?",
                (float_val, key),
            )
            updated.append(key)
        conn.commit()
        rows = conn.execute(
            "SELECT key, value, description, updated_at FROM report_config ORDER BY key"
        ).fetchall()
        return {"updated": updated, "config": [dict(r) for r in rows]}
    finally:
        conn.close()
