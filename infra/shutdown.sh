#!/usr/bin/env bash
# =============================================================================
# Centinela — Script de apagado (cierre de jornada)
# Detiene o elimina lo que consume crédito. Dos modos:
#   bash shutdown.sh          -> modo "pausa": detiene la webapp y borra el plan
#                                (el plan B1 factura por existir, no por uso;
#                                 borrarlo detiene el 100% del gasto de cómputo).
#   bash shutdown.sh --full   -> borra el grupo de recursos completo.
#                                provision.sh lo reconstruye en ~5 min.
# El almacenamiento LRS con KB de datos cuesta centavos/mes: se conserva en modo pausa.
# =============================================================================
set -euo pipefail

PROYECTO="ctn"; AMBIENTE="dev"; SUFIJO_UNICO="jj15"
RG="rg-${PROYECTO}-${AMBIENTE}"
PLAN="plan-${PROYECTO}-${AMBIENTE}"
WEBAPP="app-${PROYECTO}-ingesta-${AMBIENTE}-${SUFIJO_UNICO}"

if [ "${1:-}" = "--full" ]; then
  echo ">> Eliminando el grupo de recursos completo: $RG"
  az group delete -n "$RG" --yes --no-wait
  echo ">> Eliminación lanzada. Verifica luego con: az group exists -n $RG"
  exit 0
fi

echo ">> Deteniendo Web App y eliminando el plan (principal consumidor de crédito)"
az webapp stop -g "$RG" -n "$WEBAPP" -o none 2>/dev/null || true
az webapp delete -g "$RG" -n "$WEBAPP" 2>/dev/null || true
az appservice plan delete -g "$RG" -n "$PLAN" --yes 2>/dev/null || true

echo ">> Gasto de cómputo detenido. Storage/VNet/NSG permanecen (costo ~0)."
echo ">> Mañana: re-ejecutar provision.sh (idempotente) y re-desplegar la API."
