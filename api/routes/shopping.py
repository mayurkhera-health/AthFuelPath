from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from api.database import get_conn
from api.models import ShoppingItemCreate, ShoppingItemPatch, ShoppingPref, PersonalFood
from api.services.shopping_service import build_essentials, build_share_text, CATEGORY_ORDER, CATEGORY_LABELS
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


def _get_or_create_list(athlete_id: int, week_start: str, conn) -> int:
    conn.execute(
        "INSERT INTO shopping_lists (athlete_id, week_start) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (athlete_id, week_start),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM shopping_lists WHERE athlete_id = %s AND week_start = %s",
        (athlete_id, week_start),
    ).fetchone()["id"]


@router.get("/essentials")
def get_essentials(
    athlete_id: int = Query(...), week_start: str = Query(...), identity=Depends(require_session),
):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        return build_essentials(athlete_id, week_start, conn)
    finally:
        conn.close()


@router.get("/list")
def get_list(athlete_id: int = Query(...), week_start: str = Query(...), identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        list_id = _get_or_create_list(athlete_id, week_start, conn)
        rows = conn.execute(
            "SELECT * FROM shopping_list_items WHERE list_id = %s ORDER BY category, created_at",
            (list_id,),
        ).fetchall()
        items = [dict(r) for r in rows]

        by_cat: dict = {c: [] for c in CATEGORY_ORDER}
        for item in items:
            by_cat.setdefault(item["category"], []).append(item)

        groups = [
            {"category": cat, "label": CATEGORY_LABELS.get(cat, cat), "items": by_cat[cat]}
            for cat in CATEGORY_ORDER
            if by_cat.get(cat)
        ]
        checked_count = sum(1 for i in items if i["checked"])
        return {
            "list_id":       list_id,
            "week_start":    week_start,
            "item_count":    len(items),
            "checked_count": checked_count,
            "groups":        groups,
            "share_text":    build_share_text(week_start, items),
        }
    finally:
        conn.close()


@router.post("/list/items", status_code=201)
def add_item(data: ShoppingItemCreate, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        list_id = _get_or_create_list(data.athlete_id, data.week_start, conn)
        name = data.name.strip()
        # Case/whitespace-insensitive duplicate check — "Bananas" then
        # "bananas " used to create two separate rows instead of being
        # recognized as the same item. The first-inserted row's original
        # casing is preserved; the duplicate just returns it as-is.
        existing = conn.execute(
            "SELECT * FROM shopping_list_items WHERE list_id = %s AND LOWER(name) = LOWER(%s) AND category = %s",
            (list_id, name, data.category),
        ).fetchone()
        if existing:
            return JSONResponse(content=dict(existing), status_code=200)
        row = conn.execute(
            "INSERT INTO shopping_list_items (list_id, name, category, source) VALUES (%s, %s, %s, %s) RETURNING *",
            (list_id, name, data.category, data.source),
        ).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


@router.patch("/list/items/{item_id}")
def patch_item(item_id: int, data: ShoppingItemPatch, identity=Depends(require_session)):
    conn = get_conn()
    try:
        owner_row = conn.execute(
            "SELECT sl.athlete_id FROM shopping_list_items sli "
            "JOIN shopping_lists sl ON sl.id = sli.list_id WHERE sli.id = %s",
            (item_id,),
        ).fetchone()
        if not owner_row:
            raise HTTPException(404, "Item not found.")
        assert_owns_athlete(identity, dict(owner_row)["athlete_id"], conn)
        conn.execute(
            "UPDATE shopping_list_items SET checked = %s WHERE id = %s",
            (int(data.checked), item_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM shopping_list_items WHERE id = %s", (item_id,)
        ).fetchone()
        row = dict(updated)
        row["checked"] = bool(row["checked"])
        return row
    finally:
        conn.close()


@router.delete("/list/items/{item_id}")
def delete_item(item_id: int, identity=Depends(require_session)):
    conn = get_conn()
    try:
        owner_row = conn.execute(
            "SELECT sl.athlete_id FROM shopping_list_items sli "
            "JOIN shopping_lists sl ON sl.id = sli.list_id WHERE sli.id = %s",
            (item_id,),
        ).fetchone()
        if not owner_row:
            raise HTTPException(404, "Item not found.")
        assert_owns_athlete(identity, dict(owner_row)["athlete_id"], conn)
        conn.execute("DELETE FROM shopping_list_items WHERE id = %s", (item_id,))
        conn.commit()
        return {"deleted": True, "id": item_id}
    finally:
        conn.close()


@router.post("/prefs")
def set_pref(data: ShoppingPref, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        conn.execute(
            """INSERT INTO athlete_food_prefs (athlete_id, food_name, preference, category)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT(athlete_id, food_name) DO UPDATE SET
                 preference = excluded.preference,
                 category   = excluded.category""",
            (data.athlete_id, data.food_name, data.preference, data.category),
        )
        conn.commit()
        return {"set": True}
    finally:
        conn.close()


@router.post("/my-foods", status_code=201)
def save_personal_food(data: PersonalFood, identity=Depends(require_session)):
    conn = get_conn()
    try:
        assert_owns_athlete(identity, data.athlete_id, conn)
        if not conn.execute("SELECT id FROM athletes WHERE id = %s", (data.athlete_id,)).fetchone():
            raise HTTPException(404, "Athlete not found.")
        conn.execute(
            """INSERT INTO athlete_food_prefs (athlete_id, food_name, preference, category)
               VALUES (%s, %s, 'liked', %s)
               ON CONFLICT(athlete_id, food_name) DO UPDATE SET
                 preference = 'liked', category = excluded.category""",
            (data.athlete_id, data.name, data.category),
        )
        conn.commit()
        return {"saved": True, "name": data.name, "category": data.category}
    finally:
        conn.close()


