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

Registered at GoDaddy. Apex is canonical; www 308s to it, via the host-matched
redirect in `next.config.ts`.

Order matters and is not obvious, so it is spelled out. `NEXT_PUBLIC_SITE_URL`
is compiled into the image, so a running app cannot pick up a new value — only a
fresh deploy can. There is exactly one safe sequence.

**1. Get the addresses this app answers on.**

```bash
fly ips list -a athfuelpath-web
```

**2. Tell Fly the hostnames, so it starts watching for the DNS.**

```bash
fly certs add athfuelpath.com -a athfuelpath-web
fly certs add www.athfuelpath.com -a athfuelpath-web
```

**3. Create the records in GoDaddy** (Domain → DNS → Manage Zones).

| Type | Name | Value |
|---|---|---|
| A | `@` | the IPv4 from step 1 |
| AAAA | `@` | the IPv6 from step 1 |
| CNAME | `www` | `athfuelpath-web.fly.dev` |

Delete GoDaddy's parked records first — a new domain ships with an A record on
`@` pointing at their holding page and a CNAME on `www`. Leaving either one
means the domain resolves somewhere else half the time. Set TTL to the shortest
GoDaddy offers (600s) until this is confirmed working; raise it after.

GoDaddy does not support ALIAS/ANAME at the apex, which is why this uses a plain
A record rather than a CNAME to `.fly.dev`.

**4. Deploy immediately**, while the certificate is still issuing.

```bash
cd website && fly deploy
```

This is the whole reason for the ordering. Deploy earlier and the fly.dev host
spends the wait serving `allow: /` with canonicals pointing at a domain that
does not resolve. Deploy later and the moment the certificate issues,
athfuelpath.com is live and serving `noindex, nofollow` — because SITE_URL still
says fly.dev and `IS_PRODUCTION_SITE` is false. Certificate issuance is public,
logged in Certificate Transparency, and crawlers watch those logs, so a first
crawl can arrive within minutes. A noindex seen on the first visit is slow to
undo.

**5. Confirm, before telling anyone the address.**

```bash
fly certs show athfuelpath.com -a athfuelpath-web        Status should be Ready
curl -s https://athfuelpath.com/robots.txt               Allow: /, not Disallow: /
curl -sI https://www.athfuelpath.com/parents | head -3   308 to the apex
curl -s https://athfuelpath.com/ | grep canonical        https://athfuelpath.com
```

`Disallow: /` at step 5 means the deploy did not carry the production build arg.
Redeploy; it is not a DNS problem and waiting will not fix it.

Then paste the link into a chat app and check the preview card renders — og:image
is absolute and follows `NEXT_PUBLIC_SITE_URL`, so it breaks in exactly the same
way and is worth eyeballing once.

Search Console can wait until step 5 passes. Verifying a domain that is serving
noindex just records the noindex.

### Email on this domain

Not set up, and adding it is a DNS change on the same zone. If `purvi@athfuelpath.com`
is ever wanted, it needs MX records, which are independent of the A/AAAA records
above — mail and web routing do not interfere. Until then the waitlist sends from
the Gmail address in `GMAIL_USER`, which is a different domain and is why replies
come from that address.

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
