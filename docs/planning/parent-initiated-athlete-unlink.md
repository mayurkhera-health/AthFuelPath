# Parent-initiated athlete unlink

Agreed outside the repo (2026-09-04); recorded here before implementation per
standard practice — a decision made in conversation isn't binding on future
readers of this codebase until it's written down next to the code it governs.

## Problem

An athlete's provider identity (Apple/Google/email) can become unusable —
lost device, revoked Apple ID, changed email — with no recovery path. The
only prior recovery mechanism was `athlete-claim.tsx` (mobile) plus its
backend counterpart, which let anyone who knew a parent's email re-claim an
athlete slot. The security audit that led to its removal flagged this as
its most serious finding: recovery must never be initiated by supplying an
email address. `athlete-claim.tsx` must not return in any form.

## Design

**New parent-authenticated endpoint**, athlete-scoped, alongside the other
`{athlete_id}` routes in `api/routes/athletes.py`:

- Caller must be authenticated as that athlete's parent — reuses
  `assert_owns_athlete` (parent branch: `athletes.parent_id` match via a
  live DB lookup, already existing behavior, no change needed there).
- Hard-deletes every `auth_identities` row for that `athlete_id`
  (`apple_provider_credentials` cascades via its existing
  `ON DELETE CASCADE REFERENCES auth_identities(id)`).
- Also hard-deletes the athlete's `athlete_logins` row — this is what
  "unclaimed" means today (§ existing-flow research: no
  `athlete_logins` row = unclaimed). Without this, the athlete stays
  "claimed" and the normal link-code re-claim path has nothing to attach
  to.
- No soft-delete, no tombstone row anywhere. Audit trail lives in a new,
  separate table (`athlete_unlink_log`), never by retaining a row in
  `auth_identities`.
- After unlink: athlete is back to unclaimed state; the existing
  `athlete-claim-lookup` → OTP → `athlete-create-login/{athlete_id}` flow
  (`api/routes/auth.py`) applies unchanged — this endpoint does not
  duplicate or bypass that flow, it only clears the way back into it.
- Every unlink logged: acting parent, athlete, timestamp
  (`athlete_unlink_log`, migration `005_athlete_unlink.sql`).

**Session invalidation — the actual hard part.** Session tokens
(`api/services/session_auth.py`) are stateless HMAC-signed bearer tokens
with a 30-day TTL and **no server-side revocation mechanism of any kind**
(confirmed by repo-wide search — no denylist, no session table, no
token/session version column). `assert_owns_athlete`'s athlete-role branch
today only compares the token's own embedded `athlete_id` — zero DB
round-trip, zero way to invalidate a token before its `exp`.

Fix (approved 2026-09-04, scoped narrowly): `assert_owns_athlete`'s
athlete-role branch gains a live check that an `athlete_logins` row still
exists for that `athlete_id`. Since unlink deletes exactly that row, the
very next request on the old athlete token 403s — no new column, no
token-format change, no blacklist table. This adds one indexed SELECT to
every athlete-authenticated request that goes through
`assert_owns_athlete` (the parent-role branch already pays this same cost
on every call — this makes the two branches symmetric rather than
introducing a new cost class).

Known residual gap, not fixed by this change and out of scope: any route
that calls bare `require_session` without a following `assert_owns_athlete`
check would not re-verify against `athlete_logins`. Not currently believed
to exist for athlete-self routes (worth a follow-up grep before ship, not
blocking this design).

**Parent-side UI entry point.** Settings/account area, one tap, athlete
picker if the parent has multiple athletes. Suggested copy: *"Jake needs to
sign in again."* Confirmation step required before the destructive action
(standard for anything that ends an active session and clears provider
identities) — copy TBD at implementation time, not specified further here.

## Explicitly out of scope for this pass

- The residual `require_session`-without-`assert_owns_athlete` gap noted
  above.
- Admin-initiated unlink (a separate, already-tracked pre-launch item, not
  part of this work).
- The hardcoded deletion-notification recipient and the undefined `logger`
  reference in `api/routes/parents.py` — fixed separately, unrelated to
  this feature (commit `15d6ef1`).

## Security property this preserves

Recovery is initiated by an authenticated parent inside a live session.
Never by supplying an email address. This is the property the removed
`athlete-claim.tsx` violated; this feature must not reintroduce it in any
form, including error messages or side channels that could let an
unauthenticated caller learn whether a given email/athlete pairing exists.
