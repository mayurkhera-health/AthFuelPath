-- recipe_selections currently supports only one resolution type: a real
-- catalog recipe_id. The Meal Plan Plan-tab UI (RecipePickerSheet) and the
-- mobile RecipeSelection type have always offered two more: "I've got this"
-- (no_recipe_needed) and a parent-typed custom entry (custom_text). Neither
-- has ever had backend columns to persist into — both silently fail today.
--
-- recipe_id stays NOT NULL: the empty-string "" sentinel represents "no real
-- catalog recipe" for both no_recipe_needed and custom_text, matching the
-- existing UNIQUE (athlete_id, week_start, fueling_window_key, recipe_id)
-- constraint — a slot's "" row and a slot's real-recipe row are naturally
-- distinct, so a custom/no-recipe resolution never collides with a genuine
-- recipe pick for the same window.

ALTER TABLE recipe_selections
    ADD COLUMN no_recipe_needed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN custom_text TEXT;
