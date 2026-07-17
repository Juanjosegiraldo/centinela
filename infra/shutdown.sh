#!/usr/bin/env bash
# =============================================================================
# Centinela — End-of-day shutdown script
# Stops or deletes whatever consumes credit. Two modes:
#   bash shutdown.sh          -> "pause" mode: stops the web app and deletes
#                                the plan (a B1 plan bills for existing, not
#                                for usage; deleting it stops 100% of compute
#                                spend).
#   bash shutdown.sh --full   -> deletes the entire resource group.
#                                provision.sh rebuilds it in ~5 min.
# LRS storage holding a few KB costs cents/month: kept in pause mode.
# =============================================================================
set -euo pipefail

PROJECT="ctn"; ENVIRONMENT="dev"; UNIQUE_SUFFIX="jj15"
RG="rg-${PROJECT}-${ENVIRONMENT}"
PLAN="plan-${PROJECT}-${ENVIRONMENT}"
WEBAPP="app-${PROJECT}-ingest-${ENVIRONMENT}-${UNIQUE_SUFFIX}"

if [ "${1:-}" = "--full" ]; then
  echo ">> Deleting the entire resource group: $RG"
  az group delete -n "$RG" --yes --no-wait
  echo ">> Deletion started. Verify later with: az group exists -n $RG"
  exit 0
fi

echo ">> Stopping the Web App and deleting the plan (main credit consumer)"
az webapp stop -g "$RG" -n "$WEBAPP" -o none 2>/dev/null || true
az webapp delete -g "$RG" -n "$WEBAPP" 2>/dev/null || true
az appservice plan delete -g "$RG" -n "$PLAN" --yes 2>/dev/null || true

echo ">> Compute spend stopped. Storage/VNet/NSGs remain (cost ~0)."
echo ">> Tomorrow: re-run provision.sh (idempotent) and redeploy the API."
