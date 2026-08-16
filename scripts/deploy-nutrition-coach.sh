#!/usr/bin/env bash
# Deploy Nutrition Coach fixes + set Bedrock secrets on Fly.io.
# Prerequisites: flyctl auth login
set -euo pipefail

APP="${FLY_APP:-fuelup-youth}"
ENV_FILE="${ENV_FILE:-../AthFuelPath_Mobile/.env}"

if ! command -v flyctl >/dev/null 2>&1; then
  echo "flyctl not found. Install: curl -L https://fly.io/install.sh | sh"
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' "$ENV_FILE" | grep -E '^(AWS_|BEDROCK_)' | xargs)
fi

: "${AWS_REGION:?Set AWS_REGION in $ENV_FILE}"
: "${AWS_ACCESS_KEY_ID:?Set AWS_ACCESS_KEY_ID in $ENV_FILE}"
: "${AWS_SECRET_ACCESS_KEY:?Set AWS_SECRET_ACCESS_KEY in $ENV_FILE}"
: "${BEDROCK_MODEL_ID:=mistral.ministral-3-8b-instruct}"

echo "Setting Bedrock secrets on $APP…"
flyctl secrets set \
  "AWS_REGION=$AWS_REGION" \
  "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" \
  "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" \
  "BEDROCK_MODEL_ID=$BEDROCK_MODEL_ID" \
  -a "$APP"

echo "Deploying $APP…"
flyctl deploy -a "$APP"

echo "Checking coach health…"
curl -sf "https://${APP}.fly.dev/api/knowledge/health" | python3 -m json.tool

echo "Smoke test ask endpoint…"
curl -sf -X POST "https://${APP}.fly.dev/api/knowledge/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"What should I eat before a game?","athlete_id":1}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['answer'][:200], '…'); print('citations:', len(d.get('citations',[])))"

echo "Done."
