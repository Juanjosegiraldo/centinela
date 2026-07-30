#!/usr/bin/env bash
# =============================================================================
# Centinela — Recreate the API Web App (jj15) that is missing from rg-ctn-dev.
#
# WHY: infra/provision.sh (Week 1) normally creates app-ctn-ingest-dev-jj15, but
# the Web App is absent in the subscription and provision.sh now carries
# UNIQUE_SUFFIX=jj16 (Deliverable 19), so it cannot be re-run as-is. This script
# surgically recreates ONLY the Web App and its wiring, forced to jj15, folding
# in the Week-2 settings/roles that provision-week2.sh adds for the API.
#
# Does NOT touch storage, SQL, Cosmos, Service Bus or Key Vault (all exist and
# are locked down). Uses the existing B1 plan, so no extra compute cost.
#
# Prereq: az logged in to "Azure subscription 1". Usage: bash recreate-webapp-jj15.sh
# =============================================================================
set -euo pipefail

RG="rg-ctn-dev"
PLAN="plan-ctn-dev"
WEBAPP="app-ctn-ingest-dev-jj15"
RUNTIME="PYTHON:3.12"
VNET="vnet-ctn-dev"
SNET_APP="snet-app"
STG="stctndevjj15"

# --- 1. Create the Web App on the existing B1 plan (no extra compute cost) ----
az webapp create -g "$RG" -p "$PLAN" -n "$WEBAPP" --runtime "$RUNTIME" -o none

# --- 2. Managed identity ------------------------------------------------------
az webapp identity assign -g "$RG" -n "$WEBAPP" -o none
APP_MI=$(az webapp identity show -g "$RG" -n "$WEBAPP" --query principalId -o tsv)
echo "APP_MI=$APP_MI"

# --- 3. VNet integration (delegated subnet snet-app) --------------------------
az webapp vnet-integration add -g "$RG" -n "$WEBAPP" --vnet "$VNET" --subnet "$SNET_APP" -o none

# --- 4. App settings (Week 1 + Week 2) ----------------------------------------
az webapp config appsettings set -g "$RG" -n "$WEBAPP" --settings \
  STORAGE_ACCOUNT_URL="https://${STG}.blob.core.windows.net" \
  QUEUE_ACCOUNT_URL="https://${STG}.queue.core.windows.net" \
  TX_CONTAINER="raw-transactions" \
  DOCS_CONTAINER="verification-docs" \
  QUEUE_NAME="q-incoming-transactions" \
  MAX_UPLOAD_MB="5" \
  KEY_VAULT_URL="https://kv-ctn-dev-jj15.vault.azure.net" \
  SERVICEBUS_FQDN="sb-ctn-dev-jj15.servicebus.windows.net" \
  SBUS_TOPIC="transaction-received" \
  RATE_LIMIT_PER_MINUTE="60" \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true -o none

# --- 5. Startup (gunicorn + uvicorn worker) -----------------------------------
az webapp config set -g "$RG" -n "$WEBAPP" \
  --startup-file "gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.main:app" -o none

# --- 6. RBAC for the Web App identity (retry while the MI propagates) ----------
STG_ID=$(az storage account show -g "$RG" -n "$STG" --query id -o tsv)
VAULT_ID=$(az keyvault show -n kv-ctn-dev-jj15 --query id -o tsv)
SBUS_ID=$(az servicebus namespace show -g "$RG" -n sb-ctn-dev-jj15 --query id -o tsv)

assign() {  # tolerate "already exists"; retry while the MI propagates in Entra
  local role="$1" scope="$2" attempt out
  for attempt in 1 2 3 4 5 6; do
    if out=$(az role assignment create --assignee-object-id "$APP_MI" \
               --assignee-principal-type ServicePrincipal --role "$role" \
               --scope "$scope" -o none 2>&1); then return 0; fi
    echo "$out" | grep -qi "already exists\|RoleAssignmentExists" && return 0
    echo "   role '$role' not ready (attempt $attempt/6), waiting $((attempt*10))s..."
    sleep $((attempt*10))
  done
  echo "ERROR: could not assign '$role'" >&2; return 1
}

echo ">> Waiting for the managed identity to propagate..."
sleep 30
assign "Storage Blob Data Contributor"  "$STG_ID"     # persist tx + docs
assign "Storage Queue Data Contributor" "$STG_ID"     # enqueue to q-incoming-transactions
assign "Key Vault Secrets User"         "$VAULT_ID"    # read secrets (parity with Week 2)
assign "Azure Service Bus Data Sender"  "$SBUS_ID"     # publish to topic transaction-received

# --- 7. Verification (read-only) ----------------------------------------------
echo ">> Web App:  https://${WEBAPP}.azurewebsites.net"
az role assignment list --assignee "$APP_MI" \
  --query "[].{role:roleDefinitionName, scope:scope}" -o table

# --- Next step: deploy the API ------------------------------------------------
# cd ../api && zip -r ../api.zip . && \
#   az webapp deploy -g rg-ctn-dev -n app-ctn-ingest-dev-jj15 --src-path ../api.zip --type zip
