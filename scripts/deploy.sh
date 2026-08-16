#!/usr/bin/env bash
#
# AthFuelPath backend deploy wrapper. Wraps `flyctl deploy --app fuelup-youth` with
# two guardrails that are easy to forget:
#   1. Deploy from `main` only (the v177 incident — see CLAUDE.md).
#   2. The Performance Plate ships DARK — deploying does NOT enable it. You must
#      flip the PERFORMANCE_PLATE_ENABLED Fly secret (post-RDN sign-off).
#
# Usage:  cd ~/AthFuelPath-main && ./scripts/deploy.sh
#
set -euo pipefail

APP="fuelup-youth"
FLAG="PERFORMANCE_PLATE_ENABLED"

# ── Guardrail 1: main only ───────────────────────────────────────────────────
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
if [ "$branch" != "main" ]; then
  echo "✋ Refusing to deploy from '$branch'. Backend deploys are main-only (CLAUDE.md)."
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "⚠️  Working tree is not clean. Commit or stash before deploying."
  git status --short
  read -r -p "Deploy anyway? [y/N] " a; [ "$a" = "y" ] || [ "$a" = "Y" ] || { echo "Aborted."; exit 1; }
fi

# ── Guardrail 2: Performance Plate flag reminder ─────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "  ⚠️  PERFORMANCE PLATE FLAG — read before deploying"
echo "════════════════════════════════════════════════════════════════════════"
echo "  The Performance Plate ships DARK behind $FLAG."
echo "  Deploying does NOT turn it on. Enable it ONLY after RDN sign-off on the"
echo "  allergen tags + window→plate mapping, with:"
echo ""
echo "      fly secrets set $FLAG=true --app $APP"
echo ""
echo "  Current secret (Fly shows the NAME only, never the value):"
if fly secrets list --app "$APP" 2>/dev/null | grep -q "$FLAG"; then
  echo "    • $FLAG is SET (verify it's the value you intend)."
else
  echo "    • $FLAG is NOT set → the plate will be OFF in prod after this deploy."
fi
echo "════════════════════════════════════════════════════════════════════════"
echo ""
read -r -p "Proceed with deploy of '$APP' from main? [y/N] " ans
[ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "Aborted."; exit 1; }

# ── Deploy ───────────────────────────────────────────────────────────────────
flyctl deploy --app "$APP" "$@"

echo ""
echo "✅ Deploy complete. Reminder: if you intend the Performance Plate to be LIVE"
echo "   (and RDN has signed off), set it now:  fly secrets set $FLAG=true --app $APP"
