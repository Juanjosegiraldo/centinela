#!/usr/bin/env bash
# =============================================================================
# Centinela — Provisioning script (Week 1)
# Runs on an empty subscription with no manual intervention.
# Idempotent: `az * create` commands act as upserts.
#   Documented exception: `az role assignment create` fails if the assignment
#   already exists; tolerated with `|| true` (see ROLES section).
# Usage:  bash provision.sh
# =============================================================================
set -euo pipefail

# ----------------------------- PARAMETERS ------------------------------------
# Every variable value is declared here. Nothing is repeated in the body.
PROJECT="ctn"                       # project short code (Centinela)
ENVIRONMENT="dev"                   # dev | qa | prd
LOCATION="eastus"                   # region justified in docs/region.md
UNIQUE_SUFFIX="jj15"                # 3-6 chars: resolves global uniqueness (storage/webapp)

RG="rg-${PROJECT}-${ENVIRONMENT}"
VNET="vnet-${PROJECT}-${ENVIRONMENT}"
VNET_CIDR="10.10.0.0/16"
SNET_APP="snet-app";  SNET_APP_CIDR="10.10.1.0/26"   # /26 = 59 usable IPs (min /28 for VNet integration; /26 for Week 3 scaling)
SNET_DATA="snet-data"; SNET_DATA_CIDR="10.10.2.0/27" # Week 2 SQL/Cosmos will live here
SNET_OPS="snet-ops";   SNET_OPS_CIDR="10.10.3.0/27"  # management / future bastion
NSG_APP="nsg-${PROJECT}-app-${ENVIRONMENT}"
NSG_DATA="nsg-${PROJECT}-data-${ENVIRONMENT}"

STG="st${PROJECT}${ENVIRONMENT}${UNIQUE_SUFFIX}"     # lowercase+digits only, globally unique
DOCS_CONTAINER="verification-docs"
TX_CONTAINER="raw-transactions"
INGEST_QUEUE="q-incoming-transactions"

PLAN="plan-${PROJECT}-${ENVIRONMENT}"
PLAN_SKU="B1"                       # lowest tier supporting VNet integration (F1/D1 do not)
WEBAPP="app-${PROJECT}-ingest-${ENVIRONMENT}-${UNIQUE_SUFFIX}"  # globally unique (*.azurewebsites.net)
RUNTIME="PYTHON:3.12"

MAX_UPLOAD_MB="5"

# Entra object IDs for the human roles (optional; leave empty if they don't exist yet)
ANALYST_OID="${ANALYST_OID:-}"
AUDITOR_OID="${AUDITOR_OID:-}"
ADMIN_OID="${ADMIN_OID:-}"

# ----------------------------- RESOURCE GROUP --------------------------------
echo ">> Resource group: $RG ($LOCATION)"
az group create -n "$RG" -l "$LOCATION" -o none

# ----------------------------- NETWORK ---------------------------------------
echo ">> Virtual network and subnets"
az network vnet create -g "$RG" -n "$VNET" --address-prefix "$VNET_CIDR" -o none

az network nsg create -g "$RG" -n "$NSG_APP" -o none
az network nsg create -g "$RG" -n "$NSG_DATA" -o none

# Rule APP-100: HTTPS outbound from the app toward the data layer.
# Justification: the API persists blobs and queue messages over TLS 443.
az network nsg rule create -g "$RG" --nsg-name "$NSG_APP" -n Allow-App-To-Data-443 \
  --priority 100 --direction Outbound --access Allow --protocol Tcp \
  --source-address-prefixes "$SNET_APP_CIDR" --source-port-ranges '*' \
  --destination-address-prefixes "$SNET_DATA_CIDR" Storage \
  --destination-port-ranges 443 -o none

# Rule DATA-100: only the app subnet may reach the data layer (443).
# Justification: requirement 2.7 — nothing else reaches the data stores.
az network nsg rule create -g "$RG" --nsg-name "$NSG_DATA" -n Allow-Only-AppSubnet-443 \
  --priority 100 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes "$SNET_APP_CIDR" --source-port-ranges '*' \
  --destination-address-prefixes '*' --destination-port-ranges 443 -o none

# Rule DATA-4096: deny everything else toward the data layer by default.
az network nsg rule create -g "$RG" --nsg-name "$NSG_DATA" -n Deny-All-Inbound \
  --priority 4096 --direction Inbound --access Deny --protocol '*' \
  --source-address-prefixes '*' --source-port-ranges '*' \
  --destination-address-prefixes '*' --destination-port-ranges '*' -o none

# snet-app: delegated to App Service + Storage service endpoint (the FREE mechanism)
az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$SNET_APP" \
  --address-prefixes "$SNET_APP_CIDR" \
  --delegations Microsoft.Web/serverFarms \
  --service-endpoints Microsoft.Storage \
  --network-security-group "$NSG_APP" -o none

az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$SNET_DATA" \
  --address-prefixes "$SNET_DATA_CIDR" \
  --network-security-group "$NSG_DATA" -o none

az network vnet subnet create -g "$RG" --vnet-name "$VNET" -n "$SNET_OPS" \
  --address-prefixes "$SNET_OPS_CIDR" -o none

# ----------------------------- STORAGE ---------------------------------------
echo ">> Storage account: $STG"
az storage account create -g "$RG" -n "$STG" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --default-action Allow -o none   # locked down at the end, after creating containers/queue

# Containers and queue (Entra login, never account keys)
az storage container create --account-name "$STG" -n "$DOCS_CONTAINER" --auth-mode login -o none || true
az storage container create --account-name "$STG" -n "$TX_CONTAINER"   --auth-mode login -o none || true
az storage queue create     --account-name "$STG" -n "$INGEST_QUEUE"   --auth-mode login -o none || true

# Lifecycle: evidence to Cool at 30 days, Archive at 180; no deletion (financial retention)
az storage account management-policy create --account-name "$STG" -g "$RG" --policy '{
  "rules": [{
    "enabled": true, "name": "evidence-retention", "type": "Lifecycle",
    "definition": {
      "filters": {"blobTypes": ["blockBlob"], "prefixMatch": ["verification-docs/"]},
      "actions": {"baseBlob": {"tierToCool": {"daysAfterModificationGreaterThan": 30},
                                "tierToArchive": {"daysAfterModificationGreaterThan": 180}}}
    }}]}' -o none

# ----------------------------- APP SERVICE -----------------------------------
echo ">> Plan and Web App ($PLAN_SKU)"
az appservice plan create -g "$RG" -n "$PLAN" --sku "$PLAN_SKU" --is-linux -o none
az webapp create -g "$RG" -p "$PLAN" -n "$WEBAPP" --runtime "$RUNTIME" -o none

# Platform-managed identity (Service role, no team-managed credentials)
az webapp identity assign -g "$RG" -n "$WEBAPP" -o none
APP_MI=$(az webapp identity show -g "$RG" -n "$WEBAPP" --query principalId -o tsv)

# Virtual network integration (delegated subnet)
az webapp vnet-integration add -g "$RG" -n "$WEBAPP" --vnet "$VNET" --subnet "$SNET_APP" -o none

# Externalized configuration (requirement 2.9): none of this lives in the code
az webapp config appsettings set -g "$RG" -n "$WEBAPP" --settings \
  STORAGE_ACCOUNT_URL="https://${STG}.blob.core.windows.net" \
  QUEUE_ACCOUNT_URL="https://${STG}.queue.core.windows.net" \
  TX_CONTAINER="$TX_CONTAINER" \
  DOCS_CONTAINER="$DOCS_CONTAINER" \
  QUEUE_NAME="$INGEST_QUEUE" \
  MAX_UPLOAD_MB="$MAX_UPLOAD_MB" \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true -o none

az webapp config set -g "$RG" -n "$WEBAPP" \
  --startup-file "gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.main:app" -o none

# ----------------------------- ROLES (control vs data plane) -----------------
echo ">> Role assignments"
STG_ID=$(az storage account show -g "$RG" -n "$STG" --query id -o tsv)
RG_ID=$(az group show -n "$RG" --query id -o tsv)

# `az role assignment create` is NOT idempotent: it fails if the assignment exists.
# Documented case; the error is tolerated so the script can be re-run.
assign() { az role assignment create --assignee-object-id "$1" --assignee-principal-type "$2" \
           --role "$3" --scope "$4" -o none 2>/dev/null || true; }

# SERVICE role (web app managed identity) — data plane only:
#   Blob Data Contributor  -> operation: persist raw transaction; store verification document
#   Queue Data Contributor -> operation: enqueue transaction for the scoring engine (Week 2)
assign "$APP_MI" ServicePrincipal "Storage Blob Data Contributor"  "$STG_ID"
assign "$APP_MI" ServicePrincipal "Storage Queue Data Contributor" "$STG_ID"

# Human roles (only if object IDs were provided)
[ -n "$AUDITOR_OID" ] && assign "$AUDITOR_OID" User "Reader" "$RG_ID"                     # control plane: see everything, change nothing
[ -n "$ANALYST_OID" ] && assign "$ANALYST_OID" User "Reader" "$RG_ID"                     # sees resources, cannot modify them
[ -n "$ANALYST_OID" ] && assign "$ANALYST_OID" User "Storage Blob Data Reader" "$STG_ID"  # data plane: read case evidence
[ -n "$ADMIN_OID" ]   && assign "$ADMIN_OID"   User "Contributor" "$RG_ID"

# ----------------------------- LOCK DOWN THE DATA LAYER ----------------------
echo ">> Isolating the storage account (deny by default + subnet rule)"
az storage account network-rule add -g "$RG" --account-name "$STG" \
  --vnet-name "$VNET" --subnet "$SNET_APP" -o none || true
az storage account update -g "$RG" -n "$STG" --default-action Deny --bypass None -o none

# ----------------------------- OUTPUT ----------------------------------------
echo ""
echo "=============================================================="
echo " Centinela — provisioning complete"
echo "  Resource group : $RG ($LOCATION)"
echo "  VNet           : $VNET  app=$SNET_APP_CIDR data=$SNET_DATA_CIDR"
echo "  Storage        : $STG (access: $SNET_APP only, deny by default)"
echo "  Containers     : $TX_CONTAINER, $DOCS_CONTAINER | Queue: $INGEST_QUEUE"
echo "  Web App        : https://${WEBAPP}.azurewebsites.net (plan $PLAN_SKU)"
echo "  Managed identity: $APP_MI"
echo "  Next step      : deploy the API ->"
echo "    cd ../api && zip -r ../api.zip . && az webapp deploy -g $RG -n $WEBAPP --src-path ../api.zip --type zip"
echo "=============================================================="
