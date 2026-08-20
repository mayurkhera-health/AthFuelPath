import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from api.database import get_conn
from api.services.session_auth import require_session, assert_owns_athlete

router = APIRouter()


class MealPlanRecipeIn(BaseModel):
    """Mirrors fuelup-mobile/types/recipe.ts's Recipe shape. Was previously a
    bare `dict` — any malformed payload (missing fields, wrong types) was
    stored and re-served as-is with no validation at the API boundary."""
    id: int | None = None
    name: str
    category: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    ingredients: list[str]
    preparation_notes: str
    tags: list[str] | None = None


class ItemIn(BaseModel):
    athlete_id: int
    plan_date: str
    text: str | None = None
    recipe: MealPlanRecipeIn | None = None
    added_by: str = "parent"

    @field_validator("added_by")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("parent", "athlete"):
            raise ValueError("added_by must be 'parent' or 'athlete'")
        return v

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @model_validator(mode="after")
    def text_or_recipe(self):
        if self.recipe is None and not self.text:
            raise ValueError("text or recipe is required")
        if self.recipe is not None and not self.text:
            name = self.recipe.name.strip()
            if not name:
                raise ValueError("recipe.name is required when text is omitted")
            self.text = name
        return self


@router.post("/windows/{window_key}/items", status_code=201)
def add_item(window_key: str, body: ItemIn, identity=Depends(require_session)):
    recipe_json = json.dumps(body.recipe.model_dump()) if body.recipe is not None else None
    conn = get_conn()
    try:
        assert_owns_athlete(identity, body.athlete_id, conn)
        cur = conn.execute(
            "INSERT INTO meal_plan_selections "
            "(athlete_id, plan_date, window_key, item_text, recipe_json, added_by) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (
                body.athlete_id,
                body.plan_date,
                window_key,
                body.text,
                recipe_json,
                body.added_by,
            ),
        )
        conn.commit()
        item_id = cur.fetchone()["id"]
        out = {"id": item_id, "text": body.text, "added_by": body.added_by}
        if body.recipe is not None:
            out["recipe"] = body.recipe.model_dump()
        return out
    finally:
        conn.close()


@router.delete("/windows/{window_key}/items/{item_id}", status_code=204)
def remove_item(window_key: str, item_id: int, identity=Depends(require_session)):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, athlete_id FROM meal_plan_selections WHERE id = %s", (item_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        assert_owns_athlete(identity, dict(row)["athlete_id"], conn)
        conn.execute("DELETE FROM meal_plan_selections WHERE id = %s", (item_id,))
        conn.commit()
        return None
    finally:
        conn.close()
