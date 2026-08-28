# Parked, not deleted

Components and routes taken off the site while it is pre-launch. Excluded from
TypeScript checking (tsconfig `exclude`) and from the Docker build context
(`.dockerignore`), so nothing here is compiled or shipped — but it is committed,
so it can be switched back on rather than rewritten.

| File | Why it is here | Switch back when |
|---|---|---|
| `Plan.tsx` | The pricing card. | A price is committed. |
| `pricing-page.tsx` | `/pricing`. Restore to `src/app/pricing/page.tsx` and drop the redirect in `next.config.ts`. | Same. |

Also parked, elsewhere: `src/components/sections/Coach.tsx` and `Proof.tsx` are
unmounted from `page.tsx` but still in `src/`. `../_to_delete/MealPlan.tsx` is
superseded — its content lives in `Cook.tsx` now and it can be deleted.
