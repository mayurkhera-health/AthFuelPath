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

One, and only once the backend signup endpoint exists:

```bash
fly secrets set SIGNUP_API_URL=https://<backend>/api/auth/magic-link/request
```

Until it is set, `/api/signup` validates the form and returns
`{"ok":true,"stub":true}` without sending anything anywhere. Worth knowing before
you point real traffic at the signup page.

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
npm run build && npx next start -p 3210 &
node audit.mjs     # placeholder text, overflow, 15px type floor, tap targets, measure
```

## Known gap

`public/screens/coach-chat.webp` still shows **FuelUp Coach** in the app header and
"FuelUp provides sports nutrition guidance" in the footer. On a public
athfuelpath.com deploy that reads as a different company's product. Rebrand that
screen in the app, recapture, and replace the file before the site goes live.
