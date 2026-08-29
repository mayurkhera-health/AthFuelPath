# Deploying AthFuelPath web to Fly.io

## One-time

NOTE: every command in this file is written without trailing `#` comments,
because macOS zsh does not treat `#` as a comment in an interactive shell — it
passes it through as an argument and the command fails. Copy the lines as-is.

```bash
brew install flyctl
fly auth login
cd ~/FuelUpYouth/website
npm install
```

Then create the app and deploy. Do NOT use `fly launch` — it regenerates
`fly.toml` and would overwrite the http_service, health-check and vm settings
already tuned for this site.

```bash
fly apps create athfuelpath-web
fly deploy
```

Fly app names are globally unique. If `athfuelpath-web` is taken, pick another
name and change the `app =` line at the top of `fly.toml` to match:

```bash
fly apps create athfuelpath-web-prod
```

## Environments

`NEXT_PUBLIC_SITE_URL` is a **build-time** value. Next inlines `NEXT_PUBLIC_*` into
the client bundle, so it cannot be supplied as a runtime secret. It has to be a
Docker build arg.

Production (the default baked into `fly.toml`):

```bash
fly deploy
```

Staging, or any host that is not athfuelpath.com:

```bash
fly deploy --build-arg NEXT_PUBLIC_SITE_URL=https://athfuelpath-staging.fly.dev
```

Any origin other than `https://athfuelpath.com` serves `noindex, nofollow` and a
`Disallow: /` robots.txt. That is deliberate: a crawlable staging copy competes
with the real site for the same searches, and Google picks the winner, not you.

## Runtime secrets

**Without these the waitlist collects nothing.** Every form on the site posts to
`/api/waitlist`, which emails the entry to Purvi. With no SMTP credentials the
route returns 503, the visitor sees an error, and the only record of them is a
line in `fly logs` — which is not a waitlist.

This section previously documented `SIGNUP_API_URL` and an `/api/signup` route
that returned `{"ok":true,"stub":true}`. Both are gone. That stub is the reason
this warning is phrased the way it is: it told people to check their email and
sent nothing, and nobody noticed because the form looked like it worked.

```bash
fly secrets set GMAIL_USER=<the gmail address> GMAIL_APP_PASSWORD=<app password> -a athfuelpath-web
```

Both already exist as secrets on the **api** app — the same pair, deliberately
reused rather than adding a second mail provider. Copy them across; do not mint
new ones.

Optional, to send somewhere other than `GMAIL_USER` (comma-separated):

```bash
fly secrets set WAITLIST_TO=purvi@example.com,mayur@example.com -a athfuelpath-web
```

Setting a secret restarts the machines, so do it before or after a deploy, not
during one.

### Verify it, do not assume it

The route has never been observed delivering a real email. After the deploy,
submit the form once yourself and confirm the message arrives:

```bash
fly logs -a athfuelpath-web | grep waitlist
```

`[waitlist] ok kind=... source=...` with a masked address means it sent. Any
line containing `full entry retained` means it did **not**, and that log line is
the only copy of that person's answers.

### Limits worth knowing before you publicise the form

Five submissions per minute per IP, and 40 emails per hour per machine. Past the
hourly ceiling submissions still succeed and are still logged in full, but the
notification is skipped until the hour rolls. Both counters live in memory and
reset when a machine suspends, so with `auto_stop_machines` the real ceiling is
higher than 40. That is a bound, not a guarantee — see the comment at the top of
`src/app/api/waitlist/route.ts`. `node limiter-test.mjs` exercises both.

## Custom domain

```bash
fly certs add athfuelpath.com
fly certs add www.athfuelpath.com
fly certs show athfuelpath.com     # prints the DNS records to create
```

Deploy with the production build arg *before* pointing DNS, or the first crawl of
the live domain sees the staging noindex.

## Cost and cold starts

`auto_stop_machines = "suspend"` with `min_machines_running = 0` suspends the
machine when idle and resumes on the next request — about a second on the first
hit after a quiet spell, nothing after that. To never pay that, set
`min_machines_running = 1`.

For a launch where a deploy must not drop a request:

```bash
fly scale count 2
```

## Before a production deploy

```bash
./serve.sh          then:
node audit.mjs        placeholder text, overflow, 15px type floor, tap targets, measure
node perf.mjs         transfer weight, LCP, CLS per page
node limiter-test.mjs the waitlist rate limits
npm audit --omit=dev  expect 0 vulnerabilities
```

Use `./serve.sh`, not `npm run build && npx next start` by hand. A `next start`
left over from an earlier build serves a stylesheet hash that no longer exists,
every page renders unstyled, and `audit.mjs` reports a site-wide failure on
pages nobody touched. That has produced two false diagnoses on this project.
`serve.sh` kills the old server first and refuses to return unless the CSS hash
it is served matches the one on disk.

## Known gap

`public/screens/coach-chat.webp` still shows **FuelUp Coach** in the app header and
"FuelUp provides sports nutrition guidance" in the footer. On a public
athfuelpath.com deploy that reads as a different company's product. Rebrand that
screen in the app, recapture, and replace the file before the site goes live.
