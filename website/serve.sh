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

served=$(curl -s http://localhost:3210/coaches | grep -o '_next/static/css/[^"\\]*' | head -1 | xargs basename)
disk=$(ls .next/static/css/ | head -1)
if [ "$served" != "$disk" ]; then
  echo "STALE: server is serving $served but disk has $disk" >&2
  exit 1
fi
echo "fresh: $disk"
