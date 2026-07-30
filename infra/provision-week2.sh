#!/usr/bin/env bash
# =============================================================================
# Centinela — Week 2 provisioning (data stores, messaging, secrets, engine)
# Runs AFTER provision.sh (week 1). Same parameter style, same idempotency rules.
# Usage:  bash provision-week2.sh
# =============================================================================
set -euo pipefail

# ----------------------------- PARAMETERS ------------------------------------
PROJECT="ctn"
ENVIRONMENT="dev"
LOCATION="centralus"
UNIQUE_SUFFIX="jj15"
FUNC_LOCATION="centralus"   # Function consumption plan region; change if quota unavailable

RG="rg-${PROJECT}-${ENVIRONMENT}"
VNET="vnet-${PROJECT}-${ENVIRONMENT}"
SNET_APP="snet-app"
SNET_DATA="snet-data"
STG="st${PROJECT}${ENVIRONMENT}${UNIQUE_SUFFIX}"
WEBAPP="app-${PROJECT}-ingest-${ENVIRONMENT}-${UNIQUE_SUFFIX}"

# Transaction store (Cosmos DB)
COSMOS="cosmos-${PROJECT}-${ENVIRONMENT}-${UNIQUE_SUFFIX}"
COSMOS_DB="centinela"
COSMOS_CONTAINER="transactions"
PARTITION_KEY="/account_id"        # justified in docs/adr.md (Deliverable 2)
TTL_SECONDS=7776000                # 90 days: longest window any rule needs

# Case store (Azure SQL)
SQL_SERVER="sql-${PROJECT}-${ENVIRONMENT}-${UNIQUE_SUFFIX}"
SQL_DB="casesdb"
SQL_ADMIN="ctnadmin"

# Messaging (Service Bus Standard: topics require Standard, Basic has queues only)
SBUS="sb-${PROJECT}-${ENVIRONMENT}-${UNIQUE_SUFFIX}"
SBUS_TOPIC="transaction-received"        # EVENT distribution: notify it happened
SBUS_SUBSCRIPTION="scoring-engine"
SBUS_QUEUE="flagged-cases"               # QUEUE: guarantee processing

# Document Intelligence F0 was validated in centralus on day 1.
DI="di-${PROJECT}-${ENVIRONMENT}-${UNIQUE_SUFFIX}"

# Secrets
VAULT="kv-${PROJECT}-${ENVIRONMENT}-${UNIQUE_SUFFIX}"

# Scoring engine (Azure Function, consumption plan = pay per execution)
PLAN="plan-${PROJECT}-${ENVIRONMENT}"
FUNC="func-${PROJECT}-scoring-${ENVIRONMENT}-${UNIQUE_SUFFIX}"

# Scoring configuration (Deliverable 6: threshold NOT in code)
SCORE_THRESHOLD="50"

echo ">> Week 2 provisioning on $RG ($LOCATION)"

# ----------------------------- TRANSACTION STORE (Cosmos) --------------------
echo ">> Cosmos DB: $COSMOS (serverless)"
# Serverless: pay per request, no idle cost. Free tier is limited to one account
# per subscription; serverless keeps the cost near zero for lab volumes.
az cosmosdb create -g "$RG" -n "$COSMOS" \
  --locations regionName="$LOCATION" \
  --capabilities EnableServerless \
  --default-consistency-level Session \
  -o none

az cosmosdb sql database create -g "$RG" -a "$COSMOS" -n "$COSMOS_DB" -o none

# Partition key /account_id: the dominant query is "recent transactions of this
# account", which then reads a single partition (Deliverable 2).
# TTL: records older than the longest rule window no longer contribute.
az cosmosdb sql container create -g "$RG" -a "$COSMOS" -d "$COSMOS_DB" \
  -n "$COSMOS_CONTAINER" \
  --partition-key-path "$PARTITION_KEY" \
  --ttl "$TTL_SECONDS" \
  -o none

# ----------------------------- CASE STORE (Azure SQL) ------------------------
echo ">> Azure SQL: $SQL_SERVER / $SQL_DB"
# The admin password is generated here and stored ONLY in Key Vault.
SQL_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)Aa1!

az sql server create -g "$RG" -n "$SQL_SERVER" -l "$LOCATION" \
  --admin-user "$SQL_ADMIN" --admin-password "$SQL_PASSWORD" -o none

# Serverless with auto-pause: bills only while active, pauses after 60 min idle.
az sql db create -g "$RG" -s "$SQL_SERVER" -n "$SQL_DB" \
  --edition GeneralPurpose --compute-model Serverless \
  --family Gen5 --capacity 1 --auto-pause-delay 60 \
  --backup-storage-redundancy Local -o none

# Isolation (requirement 2.2): reachable only from the app subnet.
az network vnet subnet update -g "$RG" --vnet-name "$VNET" -n "$SNET_APP" \
  --service-endpoints Microsoft.Storage Microsoft.Sql -o none
az sql server vnet-rule create -g "$RG" -s "$SQL_SERVER" -n allow-app-subnet \
  --vnet-name "$VNET" --subnet "$SNET_APP" -o none
# Deny public access: no "allow Azure services" rule is created on purpose.
az sql server update -g "$RG" -n "$SQL_SERVER" --enable-public-network false -o none 2>/dev/null || true

# ----------------------------- MESSAGING (Service Bus) -----------------------
echo ">> Service Bus: $SBUS (Standard — topics need Standard tier)"
az servicebus namespace create -g "$RG" -n "$SBUS" -l "$LOCATION" --sku Standard -o none

# TOPIC = event distribution. The API announces "a transaction arrived" and
# moves on. Any number of subscribers may react. Fire-and-forget.
az servicebus topic create -g "$RG" --namespace-name "$SBUS" -n "$SBUS_TOPIC" -o none
az servicebus topic subscription create -g "$RG" --namespace-name "$SBUS" \
  --topic-name "$SBUS_TOPIC" -n "$SBUS_SUBSCRIPTION" -o none

# QUEUE = guaranteed processing. Flagged cases wait here until a consumer takes
# them; nothing is lost while the consumer is down. Dead-letter after 5 tries.
az servicebus queue create -g "$RG" --namespace-name "$SBUS" -n "$SBUS_QUEUE" \
  --max-delivery-count 5 --enable-dead-lettering-on-message-expiration true -o none

# ----------------------------- DOCUMENT INTELLIGENCE ------------------------
echo ">> Document Intelligence: $DI (F0)"
if ! az cognitiveservices account show -g "$RG" -n "$DI" -o none 2>/dev/null; then
  az cognitiveservices account create -g "$RG" -n "$DI" -l "$LOCATION" \
    --kind FormRecognizer --sku F0 -o none
fi

# ----------------------------- SECRETS (Key Vault) ---------------------------
echo ">> Key Vault: $VAULT"
az keyvault create -g "$RG" -n "$VAULT" -l "$LOCATION" \
  --enable-rbac-authorization true -o none 2>/dev/null || echo "   vault already exists, continuing"

MY_OID=$(az ad signed-in-user show --query id -o tsv)
SUB_ID=$(az account show --query id -o tsv)
VAULT_SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${RG}/providers/Microsoft.KeyVault/vaults/${VAULT}"

# Same retry logic as week 1: RBAC needs time to propagate.
assign() {
  local oid="$1" ptype="$2" role="$3" scope="$4" attempt out
  for attempt in 1 2 3 4 5 6; do
    if out=$(az role assignment create --assignee-object-id "$oid" \
               --assignee-principal-type "$ptype" --role "$role" \
               --scope "$scope" -o none 2>&1); then
      return 0
    fi
    if echo "$out" | grep -qi "already exists\|RoleAssignmentExists"; then
      return 0
    fi
    echo "   role '$role' not ready (attempt $attempt/6), waiting $((attempt*10))s..."
    sleep $((attempt*10))
  done
  echo "ERROR: could not assign role '$role' to $oid" >&2
  return 1
}

# The operator needs data-plane rights to write the secrets below.
assign "$MY_OID" User "Key Vault Secrets Officer" "$VAULT_SCOPE"
sleep 20

COSMOS_ENDPOINT=$(az cosmosdb show -g "$RG" -n "$COSMOS" --query documentEndpoint -o tsv)
SBUS_FQDN="${SBUS}.servicebus.windows.net"
DI_ENDPOINT=$(az cognitiveservices account show -g "$RG" -n "$DI" --query properties.endpoint -o tsv)
DI_KEY=$(az cognitiveservices account keys list -g "$RG" -n "$DI" --query key1 -o tsv)
SQL_CONN="Server=tcp:${SQL_SERVER}.database.windows.net,1433;Database=${SQL_DB};User ID=${SQL_ADMIN};Password=${SQL_PASSWORD};Encrypt=true;"

az keyvault secret set --vault-name "$VAULT" -n sql-connection-string --value "$SQL_CONN" -o none
az keyvault secret set --vault-name "$VAULT" -n cosmos-endpoint --value "$COSMOS_ENDPOINT" -o none
az keyvault secret set --vault-name "$VAULT" -n servicebus-fqdn --value "$SBUS_FQDN" -o none
az keyvault secret set --vault-name "$VAULT" -n document-intelligence-endpoint --value "$DI_ENDPOINT" -o none
az keyvault secret set --vault-name "$VAULT" -n document-intelligence-key --value "$DI_KEY" -o none
# Threshold as a secret/config value: changing it needs no redeploy (Deliverable 6).
az keyvault secret set --vault-name "$VAULT" -n score-threshold --value "$SCORE_THRESHOLD" -o none

# ----------------------------- SCORING ENGINE (Function) ---------------------
echo ">> Function App: $FUNC (consumption plan)"
# Consumption (dynamic Linux workers) is not available in this subscription in any
# tested region, so the engine runs on the existing B1 App Service plan. The
# event trigger is preserved (architectural requirement); scale-to-zero is not,
# which is acceptable since the B1 plan is already provisioned. See ADR.
az functionapp create -g "$RG" -n "$FUNC" \
  --storage-account "$STG" \
  --plan "$PLAN" \
  --runtime python --runtime-version 3.12 --functions-version 4 \
  --os-type Linux -o none

az functionapp identity assign -g "$RG" -n "$FUNC" -o none
FUNC_MI=$(az functionapp identity show -g "$RG" -n "$FUNC" --query principalId -o tsv)
APP_MI=$(az webapp identity show -g "$RG" -n "$WEBAPP" --query principalId -o tsv)

echo ">> Waiting for managed identities to propagate..."
sleep 20

COSMOS_SCOPE=$(az cosmosdb show -g "$RG" -n "$COSMOS" --query id -o tsv)
SBUS_SCOPE=$(az servicebus namespace show -g "$RG" -n "$SBUS" --query id -o tsv)

# Least privilege, one role per concrete operation:
assign "$FUNC_MI" ServicePrincipal "Key Vault Secrets User"          "$VAULT_SCOPE"  # read config
assign "$APP_MI"  ServicePrincipal "Key Vault Secrets User"          "$VAULT_SCOPE"  # read config
assign "$APP_MI"  ServicePrincipal "Azure Service Bus Data Sender"   "$SBUS_SCOPE"   # publish event
assign "$FUNC_MI" ServicePrincipal "Azure Service Bus Data Receiver" "$SBUS_SCOPE"   # consume event
assign "$FUNC_MI" ServicePrincipal "Azure Service Bus Data Sender"   "$SBUS_SCOPE"   # enqueue case
assign "$FUNC_MI" ServicePrincipal "Storage Blob Data Contributor"   \
  "$(az storage account show -g "$RG" -n "$STG" --query id -o tsv)"

# Cosmos data-plane access is granted with its own RBAC system, not Azure RBAC.
az cosmosdb sql role assignment create -g "$RG" -a "$COSMOS" \
  --role-definition-id 00000000-0000-0000-0000-000000000002 \
  --principal-id "$FUNC_MI" --scope "/" -o none 2>/dev/null || true

# ----------------------------- APP CONFIGURATION -----------------------------
echo ">> Wiring configuration (no secrets in app settings, only references)"
az functionapp config appsettings set -g "$RG" -n "$FUNC" --settings \
  KEY_VAULT_URL="https://${VAULT}.vault.azure.net" \
  COSMOS_ENDPOINT="$COSMOS_ENDPOINT" \
  COSMOS_DB="$COSMOS_DB" \
  COSMOS_CONTAINER="$COSMOS_CONTAINER" \
  SERVICEBUS_FQDN="$SBUS_FQDN" \
  SBUS_TOPIC="$SBUS_TOPIC" \
  SBUS_SUBSCRIPTION="$SBUS_SUBSCRIPTION" \
  SBUS_QUEUE="$SBUS_QUEUE" -o none

az webapp config appsettings set -g "$RG" -n "$WEBAPP" --settings \
  KEY_VAULT_URL="https://${VAULT}.vault.azure.net" \
  SERVICEBUS_FQDN="$SBUS_FQDN" \
  SBUS_TOPIC="$SBUS_TOPIC" \
  DOCUMENTINTELLIGENCE_ENDPOINT="$DI_ENDPOINT" \
  DOCUMENTINTELLIGENCE_KEY="@Microsoft.KeyVault(SecretUri=https://${VAULT}.vault.azure.net/secrets/document-intelligence-key)" \
  RATE_LIMIT_PER_MINUTE="60" -o none

WEBAPP_ID=$(az webapp show -g "$RG" -n "$WEBAPP" --query id -o tsv)
FUNC_ID=$(az functionapp show -g "$RG" -n "$FUNC" --query id -o tsv)
WEBAPP_LOCATION=$(az webapp show -g "$RG" -n "$WEBAPP" --query location -o tsv)
FUNC_LOCATION=$(az functionapp show -g "$RG" -n "$FUNC" --query location -o tsv)
SBUS_ID=$(az servicebus namespace show -g "$RG" -n "$SBUS" --query id -o tsv)
SBUS_SUBSCRIPTION_RESOURCE="${SBUS_ID}/topics/${SBUS_TOPIC}/subscriptions/${SBUS_SUBSCRIPTION}"

create_autoscale_setting() {
  local autoscale_name="$1"
  local target_resource_id="$2"
  local target_location="$3"
  local metric_name="$4"
  local metric_resource_uri="$5"
  local scale_out_threshold="$6"
  local scale_in_threshold="$7"
  local json_path
  json_path=$(mktemp)

  cat > "$json_path" <<EOF
{
  "location": "$target_location",
  "properties": {
    "targetResourceUri": "$target_resource_id",
    "enabled": true,
    "profiles": [
      {
        "name": "default",
        "capacity": { "minimum": "1", "maximum": "3", "default": "1" },
        "rules": [
          {
            "metricTrigger": {
              "metricName": "$metric_name",
              "metricResourceUri": "$metric_resource_uri",
              "timeGrain": "PT1M",
              "statistic": "Average",
              "timeWindow": "PT10M",
              "timeAggregation": "Average",
              "operator": "GreaterThan",
              "threshold": $scale_out_threshold
            },
            "scaleAction": {
              "direction": "Increase",
              "type": "ChangeCount",
              "value": "1",
              "cooldown": "PT5M"
            }
          },
          {
            "metricTrigger": {
              "metricName": "$metric_name",
              "metricResourceUri": "$metric_resource_uri",
              "timeGrain": "PT1M",
              "statistic": "Average",
              "timeWindow": "PT10M",
              "timeAggregation": "Average",
              "operator": "LessThan",
              "threshold": $scale_in_threshold
            },
            "scaleAction": {
              "direction": "Decrease",
              "type": "ChangeCount",
              "value": "1",
              "cooldown": "PT5M"
            }
          }
        ]
      }
    ],
    "notifications": []
  }
}
EOF

  az rest --method put \
    --uri "https://management.azure.com${target_resource_id}/providers/Microsoft.Insights/autoscalesettings/${autoscale_name}?api-version=2022-10-01" \
    --body @"$json_path" -o none

  rm -f "$json_path"
}

create_autoscale_setting "${WEBAPP}-autoscale" "$WEBAPP_ID" "$WEBAPP_LOCATION" "HttpQueueLength" "$WEBAPP_ID" 10 3
create_autoscale_setting "${FUNC}-autoscale" "$FUNC_ID" "$FUNC_LOCATION" "ActiveMessages" "$SBUS_SUBSCRIPTION_RESOURCE" 20 3

# ----------------------------- OUTPUT ----------------------------------------
echo ""
echo "=============================================================="
echo " Centinela — Week 2 provisioning complete"
echo "  Cosmos DB    : $COSMOS / $COSMOS_DB / $COSMOS_CONTAINER"
echo "                 partition=$PARTITION_KEY  ttl=${TTL_SECONDS}s  consistency=Session"
echo "  Azure SQL    : ${SQL_SERVER}.database.windows.net / $SQL_DB (subnet-only)"
echo "  Service Bus  : $SBUS"
echo "                 topic=$SBUS_TOPIC (event)  queue=$SBUS_QUEUE (guaranteed)"
echo "  Doc Intel    : $DI (F0)"
echo "  Key Vault    : $VAULT (threshold=$SCORE_THRESHOLD, changeable without redeploy)"
echo "  Function App : $FUNC (scoring engine)"
echo "  SQL password : stored ONLY in Key Vault secret 'sql-connection-string'"
echo "  Next steps   : 1) create the case tables (docs/schema.sql)"
echo "                 2) deploy the scoring function"
echo "                 3) add event publishing to the API (events.py)"
echo "=============================================================="
