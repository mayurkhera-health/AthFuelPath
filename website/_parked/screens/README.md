# Screens not on the site

Moved out of `public/screens/` on 2026-08-29. Nothing referenced any of them —
verified against `src/`, the built server output, and the rendered HTML of every
route, not just by grepping the source.

They were moved rather than deleted, and moved rather than left alone, because
`public/` is a published directory: every file in it is a fetchable URL whether
or not a page links to it. `https://…/screens/recipe.webp` was serving an app
screen that has never appeared on the site. `_parked/` is excluded from the
Docker build context (`.dockerignore`) and from TypeScript (`tsconfig.json`), so
nothing here ships or compiles — but it is committed, so nothing is lost.

To put one back on the site: move the file to `public/screens/` and reference it
from a page. Nothing else needs changing.

## Finished assets of screens the site does not show

These are not sources. They are optimised, ready to use, and the reason this
folder exists rather than a `git rm`.

| File | What it shows | Why it is here |
|---|---|---|
| `coach-chat.webp` | The Fuel Coach answering "practice in 2 hrs, I'm particular about textures" | `/coaches` renders its content as **text** instead — see the note above `coachChat` in `site.ts`, which transcribes it word for word for accessibility and indexing. **Do not put this on the site as-is:** the header reads "FuelUp Coach" and the footer "FuelUp provides sports nutrition guidance", which is the wrong brand. Rebrand in the app and recapture first. |
| `recipe.webp` | A single recipe screen | Never had a section. `/parents` shows the meal-plan and grocery screens instead. |
| `mealplan-week.webp` | The week view of the meal plan | Superseded on `/parents` by `mealplan-choose.webp`, which shows the act of filling a window rather than the finished grid. |

`/coaches` currently renders no product screenshot at all. `coach-chat.webp` is
the obvious fix for that, once it is rebranded.

## Capture sources

Lossless originals of three WebPs that are live. Same dimensions as their WebP
counterparts — these are what the WebPs were encoded from.

| File | WebP it produced | Size |
|---|---|---|
| `today.png` (792×1614) | `public/screens/today.webp` | 484K → 57K |
| `mealplan-choose.png` (792×1600) | `public/screens/mealplan-choose.webp` | 472K → 59K |
| `mealplan-week.png` (792×1344) | `mealplan-week.webp`, also parked | 384K → 46K |

Keep them only as a convenience. The real source is the app — recapturing beats
re-deriving from an ageing PNG, and these will drift out of date the first time
a screen changes. If a lossless original is ever wanted for print, a deck or App
Store shots, the long-term home is the `AthFuelPath Asset Library` folder, not
this repo.
