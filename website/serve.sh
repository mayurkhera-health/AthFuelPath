#!/usr/bin/env bash
# Rebuild and restart the audit server on :3210, then PROVE it is not stale.
#
# A `next start` left running from a previous build serves a CSS hash that no
# longer exists on disk. Every page then renders unstyled and audit.mjs reports
# a mass failure across pages nobody touched. That has cost this project two
# false diagnoses. This script kills first, starts second, and refuses to return
# success unless the hash the server hands out is the one in .next.
set -euo pipefail
cd "$(dirname "$0")"

# The *.mjs audits import playwright, which is deliberately NOT in package.json.
# Dockerfile runs `npm ci`, which installs devDependencies, so listing it there
# would pull a browser download into every production image build. It lives as
# an unsaved install instead — and `npm install` prunes it as extraneous, which
# is how it vanished once mid-audit. Reinstate it silently if it is missing.
[ -d node_modules/playwright ] || npm install --no-save playwright >/dev/null 2>&1

npm run build >/tmp/build.log 2>&1 || { tail -30 /tmp/build.log; exit 1; }
pkill -9 -f next-server 2>/dev/null || true
pkill -9 -f "next start" 2>/dev/null || true
sleep 2
nohup npx next start -p 3210 >/tmp/next3210.log 2>&1 &
for _ in $(seq 1 30); do
  sleep 1
  curl -sf -o /dev/null http://localhost:3210/ && break
done

# Compare the SET of stylesheets the page asks for against the SET on disk.
#
# This used to compare `head -1` of each, which worked only while the build
# emitted exactly one CSS file. The moment it emitted two — a small route chunk
# alongside the main sheet — the first <link> in the HTML and the alphabetically
# first file on disk stopped being the same file, and this reported STALE on a
# perfectly fresh server. A staleness guard that cries wolf is worse than none,
# because the next real warning gets waved through.
#
# What actually proves freshness: every hash the page references exists on disk.
# A genuinely stale server references a hash the new build deleted, which this
# still catches.
served=$(curl -s http://localhost:3210/coaches | grep -o '_next/static/css/[^"\\]*' | xargs -n1 basename | sort -u)
[ -n "$served" ] || { echo "STALE: page referenced no stylesheet at all" >&2; exit 1; }
missing=""
for f in $served; do
  [ -f ".next/static/css/$f" ] || missing="$missing $f"
done
if [ -n "$missing" ]; then
  echo "STALE: server references$missing which is not in .next/static/css/" >&2
  echo "       disk has: $(ls .next/static/css/ | tr '\n' ' ')" >&2
  exit 1
fi
echo "fresh: $(echo "$served" | tr '\n' ' ')"
