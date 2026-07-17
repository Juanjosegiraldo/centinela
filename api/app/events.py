"""
PUNTO DE INSERCIÓN — Semana 2 (requisito 2.9, "preparación para la mensajería").

Hoy `publicar_transaccion_recibida` no hace nada. En la Semana 2 su cuerpo
publicará el evento (p. ej. escribir el mensaje en la cola / Service Bus) SIN
tocar el endpoint: el flujo del endpoint ya lo invoca tras persistir.
"""


def publicar_transaccion_recibida(transaction_id: str) -> None:
    # Semana 2: encolar/publicar evento "transaccion_recibida" aquí.
    return None
