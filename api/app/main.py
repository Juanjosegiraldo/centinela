"""
Centinela — API de ingesta (Semana 1).

Comportamiento requerido, en orden (2.9):
  1. Recibir  2. Validar contrato  3. Persistir cruda  4. Acuse de recibo.
NO consulta historial, NO calcula scores, NO aplica reglas, NO abre casos.

Tabla de códigos de estado (entregable 18):
  202  Transacción válida aceptada y persistida (acuse asíncrono).
  400  JSON malformado / campos ausentes / tipos incorrectos / campos extra /
       monto fuera de rango / marca de tiempo futura / coordenadas inválidas.
  409  Documento duplicado (mismo nombre destino ya existe).
  413  Documento excede el tamaño máximo.
  415  Tipo de archivo no permitido (validado por contenido real, no extensión).
  422  (Se normaliza a 400: no exponemos detalles internos de validación
       más allá del campo y motivo genérico.)
  500  Error interno; el cuerpo nunca expone trazas ni nombres de recursos.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .contract import Transaccion
from . import storage, events

app = FastAPI(title="Centinela — API de ingesta", version="0.1.0")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "5")) * 1024 * 1024

# Validación por contenido real (magic bytes), no por extensión (2.10)
FIRMAS = {
    b"%PDF": ("application/pdf", "pdf"),
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}


@app.exception_handler(RequestValidationError)
async def validacion(_req: Request, exc: RequestValidationError):
    # Mensaje útil para el emisor sin exponer internals del sistema.
    detalles = [
        {"campo": ".".join(str(p) for p in e["loc"] if p != "body"),
         "motivo": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=400,
                        content={"error": "payload_invalido", "detalles": detalles})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transactions", status_code=202)
def ingerir(tx: Transaccion):
    # 3. Persistir la transacción cruda (idempotente por transaction_id)
    registro = tx.model_dump(mode="json")
    registro["received_at"] = datetime.now(timezone.utc).isoformat()
    storage.persistir_transaccion(str(tx.transaction_id), json.dumps(registro))

    # Punto de inserción Semana 2 (no-op hoy): publicar evento tras persistir.
    events.publicar_transaccion_recibida(str(tx.transaction_id))

    # 4. Acuse de recibo. La confirmación se emite DESPUÉS de persistir:
    #    es el único punto de la secuencia donde el acuse es seguro (2.12).
    return {"status": "accepted", "transaction_id": str(tx.transaction_id)}


@app.post("/cases/{case_id}/documents", status_code=201)
async def cargar_documento(case_id: str, file: UploadFile = File(...)):
    data = await file.read()

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail={"error": "documento_excede_tamano_maximo"})

    tipo = next(((ct, ext) for magia, (ct, ext) in FIRMAS.items()
                 if data.startswith(magia)), None)
    if tipo is None:
        raise HTTPException(415, detail={"error": "tipo_de_archivo_no_permitido"})
    content_type, ext = tipo

    # El nombre destino lo genera el SISTEMA (2.10): caso + uuid. El nombre del
    # archivo del usuario es un vector de ataque conocido y no se utiliza.
    nombre = f"{case_id}/{uuid.uuid4()}.{ext}"
    try:
        storage.guardar_documento(nombre, data, content_type)
    except Exception:
        raise HTTPException(409, detail={"error": "conflicto_al_guardar"})

    return {"status": "stored", "blob": nombre}
