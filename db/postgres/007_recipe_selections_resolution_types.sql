-- recipe_selections currently supports only one resolution type: a real
-- catalog recipe_id. The Meal Plan Plan-tab UI (RecipePickerSheet) and the
-- mobile RecipeSelection type have always offered two more: "I've got this"
-- (no_recipe_needed) and a parent-typed custom entry (custom_text). Neither
-- has ever had backend columns to persist into — both silently fail today.
--
-- recipe_id stays NOT NULL: the empty-string "" sentinel represents "no real
-- catalog recipe" for both no_recipe_needed and custom_text.
--
-- Corrected before this migration ever shipped (still unapplied everywhere
-- but the local dev DB): the existing UNIQUE (athlete_id, week_start,
-- fueling_window_key, recipe_id) constraint does not include selection_date,
-- so the same recipe_id chosen for the same window on two different days in
-- one week (Monday breakfast=R001, Tuesday breakfast=R001) collides — and
-- because no_recipe_needed/custom_text both share the recipe_id="" sentinel,
-- ANY two of them for the same window in the same week collide regardless of
-- date. Build 67's actual product model is one resolution per
-- (athlete, date, window), not per (athlete, week, window, recipe) — slot
-- identity must never include recipe_id. Since 007 has not shipped, this
-- replaces the wrong constraint outright rather than adding a migration 008
-- to fix a migration that was never live.

ALTER TABLE recipe_selections
    ADD COLUMN no_recipe_needed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN custom_text TEXT;

ALTER TABLE recipe_selections
    DROP CONSTRAINT recipe_selections_athlete_id_week_start_fueling_window_key__key;

ALTER TABLE recipe_selections
    ADD CONSTRAINT recipe_selections_athlete_id_week_start_selection_date_fue_key
    UNIQUE (athlete_id, week_start, selection_date, fueling_window_key);
