#!/usr/bin/env bash
# =============================================================================
# Centinela — Script de aprovisionamiento (Semana 1)
# Ejecutable sobre una suscripción vacía, sin intervención manual.
# Idempotente: los comandos `az * create` actúan como upsert.
#   Excepción documentada: `az role assignment create` falla si la asignación
#   ya existe; se tolera con `|| true` (ver sección ROLES).
# Uso:  bash provision.sh
# =============================================================================
set -euo pipefail

# ----------------------------- PARÁMETROS ------------------------------------
# Todos los valores variables se declaran aquí. Nada se repite en el cuerpo.
PROYECTO="ctn"                      # abreviatura del proyecto (Centinela)
AMBIENTE="dev"                      # dev | qa | prd
LOCATION="eastus"                   # región justificada en docs/region.md
SUFIJO_UNICO="jj15"                 # 3-6 chars: resuelve unicidad global (storage/webapp)

RG="rg-${PROYECTO}-${AMBIENTE}"
VNET="vnet-${PROYECTO}-${AMBIENTE}"
VNET_CIDR="10.10.0.0/16"
SNET_APP="snet-app";  SNET_APP_CIDR="10.10.1.0/26"   # /26 = 59 IPs útiles (mín. /28 para VNet integration; /26 por escalado S3)
SNET_DATA="snet-data"; SNET_DATA_CIDR="10.10.2.0/27" # SQL/Cosmos de la Semana 2 vivirán aquí
SNET_OPS="snet-ops";   SNET_OPS_CIDR="10.10.3.0/27"  # gestión / futuro bastión
NSG_APP="nsg-${PROYECTO}-app-${AMBIENTE}"
NSG_DATA="nsg-${PROYECTO}-data-${AMBIENTE}"

STG="st${PROYECTO}${AMBIENTE}${SUFIJO_UNICO}"        # solo minúsculas+números, único global
CONTENEDOR_DOCS="docs-verificacion"
CONTENEDOR_TX="transacciones-crudas"
COLA_INGESTA="q-transacciones-entrantes"

PLAN="plan-${PROYECTO}-${AMBIENTE}"
PLAN_SKU="B1"                       # nivel más bajo con VNet integration (F1/D1 no la soportan)
WEBAPP="app-${PROYECTO}-ingesta-${AMBIENTE}-${SUFIJO_UNICO}"  # único global (*.azurewebsites.net)
RUNTIME="PYTHON:3.12"

MAX_UPLOAD_MB="5"

# Object IDs de Entra para los roles humanos (opcional; dejar vacío si aún no existen)
OID_ANALISTA="${OID_ANALISTA:-}"
OID_AUDITOR="${OID_AUDITOR:-}"
OID_ADMIN="${OID_ADMIN:-}"

# ----------------------------- GRUPO DE RECURSOS -----------------------------
echo ">> Grupo de recursos: $RG ($LOCATION)"
az group create -n "$RG" -l "$LOCATION" -o none

# ----------------------------- RED -------------------------------------------
echo ">> Red virtual y subredes"
az network vnet create -g "$RG" -n "$VNET" --address-prefix "$VNET_CIDR" -o none

az network nsg create -g "$RG" -n "$NSG_APP" -o none
az network nsg create -g "$RG" -n "$NSG_DATA" -o none

# Regla APP-100: HTTPS saliente de la app hacia la capa de datos.
# Justificación: la API persiste blobs y mensajes de cola sobre TLS 443.
az network nsg rule create -g "$RG" --nsg-name "$NSG_APP" -n Allow-App-To-Data-443 \
  --priority 100 --direction Outbound --access Allow --protocol Tcp \
  --source-address-prefixes "$SNET_APP_CIDR" --source-port-ranges '*' \
  --destination-address-prefixes "$SNET_DATA_CIDR" Storage \
  --destination-port-ranges 443 -o none

# Regla DATA-100: solo la subred de aplicación entra a la capa de datos (443).
# Justificación: requisito 2.7 — nadie más alcanza los almacenes.
az network nsg rule create -g "$RG" --nsg-name "$NSG_DATA" -n Allow-Only-AppSubnet-443 \
  --priority 100 --direction Inbound --access Allow --protocol Tcp \
  --source-address-prefixes "$SNET_APP_CIDR" --source-port-ranges '*' \
  --destination-address-prefixes '*' --destination-port-ranges 443 -o none

# Regla DATA-4096: denegar por defecto todo lo demás hacia datos.
az network nsg rule create -g "$RG" --nsg-name "$NSG_DATA" -n Deny-All-Inbound \
  --priority 4096 --direction Inbound --access Deny --protocol '*' \
  --source-address-prefixes '*' --source-port-ranges '*' \
  --destination-address-prefixes '*' --destination-port-ranges '*' -o none

# snet-app: delegada a App Service + service endpoint de Storage (mecanismo SIN costo)
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

# ----------------------------- ALMACENAMIENTO --------------------------------
echo ">> Cuenta de almacenamiento: $STG"
az storage account create -g "$RG" -n "$STG" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --default-action Allow -o none   # se cierra al final, tras crear contenedores/cola

# Contenedores y cola (con login de Entra, no con claves)
az storage container create --account-name "$STG" -n "$CONTENEDOR_DOCS" --auth-mode login -o none || true
az storage container create --account-name "$STG" -n "$CONTENEDOR_TX"   --auth-mode login -o none || true
az storage queue create     --account-name "$STG" -n "$COLA_INGESTA"    --auth-mode login -o none || true

# Ciclo de vida: evidencia a Cool a 30 días, Archive a 180; sin borrado (retención financiera)
az storage account management-policy create --account-name "$STG" -g "$RG" --policy '{
  "rules": [{
    "enabled": true, "name": "evidencia-retencion", "type": "Lifecycle",
    "definition": {
      "filters": {"blobTypes": ["blockBlob"], "prefixMatch": ["docs-verificacion/"]},
      "actions": {"baseBlob": {"tierToCool": {"daysAfterModificationGreaterThan": 30},
                                "tierToArchive": {"daysAfterModificationGreaterThan": 180}}}
    }}]}' -o none

# ----------------------------- APP SERVICE -----------------------------------
echo ">> Plan y Web App ($PLAN_SKU)"
az appservice plan create -g "$RG" -n "$PLAN" --sku "$PLAN_SKU" --is-linux -o none
az webapp create -g "$RG" -p "$PLAN" -n "$WEBAPP" --runtime "$RUNTIME" -o none

# Identidad gestionada por la plataforma (rol Servicio, sin credenciales propias)
az webapp identity assign -g "$RG" -n "$WEBAPP" -o none
APP_MI=$(az webapp identity show -g "$RG" -n "$WEBAPP" --query principalId -o tsv)

# Integración con la red virtual (subred delegada)
az webapp vnet-integration add -g "$RG" -n "$WEBAPP" --vnet "$VNET" --subnet "$SNET_APP" -o none

# Configuración externalizada (requisito 2.9): nada de esto vive en el código
az webapp config appsettings set -g "$RG" -n "$WEBAPP" --settings \
  STORAGE_ACCOUNT_URL="https://${STG}.blob.core.windows.net" \
  QUEUE_ACCOUNT_URL="https://${STG}.queue.core.windows.net" \
  CONTAINER_TX="$CONTENEDOR_TX" \
  CONTAINER_DOCS="$CONTENEDOR_DOCS" \
  QUEUE_NAME="$COLA_INGESTA" \
  MAX_UPLOAD_MB="$MAX_UPLOAD_MB" \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true -o none

az webapp config set -g "$RG" -n "$WEBAPP" \
  --startup-file "gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.main:app" -o none

# ----------------------------- ROLES (plano de datos vs control) -------------
echo ">> Asignaciones de rol"
STG_ID=$(az storage account show -g "$RG" -n "$STG" --query id -o tsv)
RG_ID=$(az group show -n "$RG" --query id -o tsv)

# `az role assignment create` NO es idempotente: falla si la asignación existe.
# Caso documentado; se tolera el error para permitir re-ejecución del script.
asignar() { az role assignment create --assignee-object-id "$1" --assignee-principal-type "$2" \
            --role "$3" --scope "$4" -o none 2>/dev/null || true; }

# Rol SERVICIO (identidad gestionada de la webapp) — solo plano de datos:
#   Blob Data Contributor  -> operación: persistir transacción cruda y cargar documento
#   Queue Data Contributor -> operación: encolar transacción para el motor (Semana 2)
asignar "$APP_MI" ServicePrincipal "Storage Blob Data Contributor"  "$STG_ID"
asignar "$APP_MI" ServicePrincipal "Storage Queue Data Contributor" "$STG_ID"

# Roles humanos (si se pasaron los Object IDs)
[ -n "$OID_AUDITOR" ]  && asignar "$OID_AUDITOR"  User "Reader" "$RG_ID"                       # plano de control: ver todo, tocar nada
[ -n "$OID_ANALISTA" ] && asignar "$OID_ANALISTA" User "Reader" "$RG_ID"                       # ve recursos, no los modifica
[ -n "$OID_ANALISTA" ] && asignar "$OID_ANALISTA" User "Storage Blob Data Reader" "$STG_ID"    # plano de datos: leer evidencia
[ -n "$OID_ADMIN" ]    && asignar "$OID_ADMIN"    User "Contributor" "$RG_ID"

# ----------------------------- CIERRE DE LA CAPA DE DATOS --------------------
echo ">> Aislando la cuenta de almacenamiento (deny por defecto + regla de subred)"
az storage account network-rule add -g "$RG" --account-name "$STG" \
  --vnet-name "$VNET" --subnet "$SNET_APP" -o none || true
az storage account update -g "$RG" -n "$STG" --default-action Deny --bypass None -o none

# ----------------------------- SALIDA ----------------------------------------
echo ""
echo "=============================================================="
echo " Centinela — aprovisionamiento completado"
echo "  Grupo de recursos : $RG ($LOCATION)"
echo "  VNet              : $VNET  app=$SNET_APP_CIDR data=$SNET_DATA_CIDR"
echo "  Storage           : $STG (acceso: solo $SNET_APP, deny por defecto)"
echo "  Contenedores      : $CONTENEDOR_TX, $CONTENEDOR_DOCS | Cola: $COLA_INGESTA"
echo "  Web App           : https://${WEBAPP}.azurewebsites.net (plan $PLAN_SKU)"
echo "  Identidad gestion.: $APP_MI"
echo "  Siguiente paso    : desplegar la API ->"
echo "    cd ../api && zip -r ../api.zip . && az webapp deploy -g $RG -n $WEBAPP --src-path ../api.zip --type zip"
echo "=============================================================="
