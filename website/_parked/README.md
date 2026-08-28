# Parked, not deleted

Routes and components taken off the site while AthFuelPath is closed to
families. Excluded from TypeScript checking (`tsconfig.json` → `exclude`) and
from the Docker build context (`.dockerignore`), so nothing here compiles or
ships — but it is committed, so each piece can be switched back on rather than
rewritten from memory.

| File | Restore to | Switch back on when |
|---|---|---|
| `Plan.tsx` | `src/components/sections/Plan.tsx` | A price is committed. |
| `pricing-page.tsx` | `src/app/pricing/page.tsx` | Same. |
| `login-page.tsx` | `src/app/login/page.tsx` | Parents have accounts to log into. |
| `signup-SignupForm.tsx` | `src/app/signup/SignupForm.tsx` | Real signup returns — see caveat below. |
| `signup-route.ts` | `src/app/api/signup/route.ts` | Same. |

Each one also needs its redirect removed from `next.config.ts` and its path
added back to `src/app/sitemap.ts`. For login, restore `nav.login` in
`src/content/site.ts` from `null` to `{ label: cta.login, href: "/login" }`;
`Header.tsx` already guards on it and needs no change.

## Before restoring signup, read this

`signup-SignupForm.tsx` and `signup-route.ts` are the versions that shipped a
silent failure: the route returned `{"ok":true,"stub":true}` and the form told
the parent "check your email" while nothing was sent. Do not restore them as-is.

They also assume a magic-link endpoint that was never built. What exists is:

- `POST /api/parents/` — creates the account (`full_name`, `email`,
  `consent_confirmed`; **no phone field** — the form's phone number is dropped)
- `POST /api/parents/request-otp` — sends a **6-digit code**, and 404s if the
  parent does not already exist
- `POST /api/parents/verify-otp` — validates it

So signup is a two-call sequence, the email carries a code rather than a link,
and there is no code-entry screen on the website. The confirmation copy has to
change with the wiring, and the partial-failure case (account created, code not
sent) needs its own message.

Also unmounted but still in `src/`, not here:
`components/sections/Coach.tsx` and `Proof.tsx`. `../_to_delete/MealPlan.tsx`
is superseded — its content lives in `Cook.tsx` and it can be deleted.
