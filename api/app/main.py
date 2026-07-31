"""
Centinela — Ingestion API (Week 1).

Required behavior, in order (requirement 2.9):
  1. Receive  2. Validate contract  3. Persist raw  4. Acknowledge.
It does NOT query history, compute scores, apply rules or open cases.

Status code table (Deliverable 18):
  202  Valid transaction accepted and persisted (asynchronous acknowledgment).
  400  Malformed JSON / missing fields / wrong types / extra fields /
       amount out of range / future timestamp / invalid coordinates.
  409  Duplicate document (target name already exists).
  413  Document exceeds the maximum size.
  415  File type not allowed (validated by real content, not extension).
  422  (Normalized to 400: we expose only the field and a generic reason,
       never internal validation details.)
  500  Internal error; the body never exposes traces or resource names.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Header, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import auth
from .contract import Transaction
from . import storage, events, ratelimit, scored

app = FastAPI(title="Centinela — Ingestion API", version="0.1.0")

# CORS: let the browser demo console call the ingestion API. Origins come from
# CORS_ALLOWED_ORIGINS (comma-separated app setting); default is the local
# Next.js dev server. No credentials are sent, so the allowlist stays explicit
# and we never fall back to a wildcard "*".
_cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "5")) * 1024 * 1024

# Validation by real content (magic bytes), never by extension (requirement 2.10)
SIGNATURES = {
    b"%PDF": ("application/pdf", "pdf"),
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
}

def _require_analyst_access(x_ms_client_principal: str | None = Header(default=None)) -> None:
    try:
        auth.require_analyst_access(x_ms_client_principal)
    except ValueError as exc:
        raise HTTPException(401, detail={"error": str(exc)}) from exc
    except PermissionError as exc:
        raise HTTPException(403, detail={"error": "analyst_role_required"})


@app.middleware("http")
async def _rate_limit_transactions(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/transactions":
        allowed, details = ratelimit.check_request(request)
        if not allowed:
            return JSONResponse(status_code=429,
                                content={"error": "rate_limit_exceeded", **details})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    # Useful message for the issuer without exposing system internals.
    details = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"),
         "reason": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=400,
                        content={"error": "invalid_payload", "details": details})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transactions", status_code=202)
def ingest(tx: Transaction):
    # 3. Persist the raw transaction (idempotent by transaction_id)
    record = tx.model_dump(mode="json")
    record["received_at"] = datetime.now(timezone.utc).isoformat()
    storage.persist_transaction(str(tx.transaction_id), json.dumps(record))

    # Week 2 insertion point: publish the complete transaction record after persistence.
    events.publish_transaction_received(record)

    # W3-09: record the API stage of the transaction's trace. Auxiliary — a
    # trace failure must never fail the ingestion that was already persisted.
    try:
        storage.persist_trace(str(tx.transaction_id), {
            "transaction_id": str(tx.transaction_id),
            "received_at": record["received_at"],
            "source": "api",
            "status": "accepted",
        })
    except Exception:
        logging.warning("trace persistence failed for %s", tx.transaction_id)

    # 4. Acknowledge. The acknowledgment is issued AFTER persisting:
    #    the only point in the sequence where it is safe (requirement 2.12).
    return {"status": "accepted", "transaction_id": str(tx.transaction_id)}


@app.get("/transactions/{transaction_id}")
def get_transaction_score(transaction_id: str):
    """Read-side endpoint: return the engine's scored result for a transaction.

    The engine scores asynchronously, so callers poll this: `scored: false`
    (status "pending") until the analysis lands in Cosmos, then the real score,
    case decision and triggered rules.
    """
    record = scored.get_scored_transaction(transaction_id)
    if record is None:
        return {"transaction_id": transaction_id, "scored": False, "status": "pending"}
    return {
        "transaction_id": transaction_id,
        "scored": True,
        "score": record.get("score"),
        "case_enqueued": record.get("case_enqueued"),
        "rules_triggered": record.get("rules_triggered", []),
        "scored_at": record.get("scored_at"),
    }


@app.post("/cases/{case_id}/documents", status_code=201)
async def upload_document(case_id: str, file: UploadFile = File(...)):
    data = await file.read()

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail={"error": "document_exceeds_max_size"})

    document_name = f"{uuid.uuid4()}.bin"
    target_name = storage.document_blob_name(case_id, document_name)
    detected = next(((ct, ext) for magic, (ct, ext) in SIGNATURES.items()
                     if data.startswith(magic)), None)

    if detected is None:
        # W3-07: the failure must not leave the case in an indeterminate state —
        # record the rejected attempt (queryable via GET /cases/{id}/documents)
        # and notify the analyst, but keep the CONTRACT status code (415,
        # Deliverable 18) instead of a misleading 201.
        storage.append_case_document_state(
            case_id,
            document_name,
            status="rejected",
            outcome="unsupported_format",
            notification="Analyst notified: document rejected because the format was not recognized.",
            metadata={"content_length": len(data)},
        )
        raise HTTPException(415, detail={
            "error": "file_type_not_allowed",
            "outcome": "unsupported_format",
            "notification": "Analyst notified: document rejected because the format was not recognized.",
        })

    content_type, ext = detected
    document_name = f"{uuid.uuid4()}.{ext}"
    target_name = storage.document_blob_name(case_id, document_name)
    try:
        storage.store_document(target_name, data, content_type)
    except Exception:
        raise HTTPException(409, detail={"error": "storage_conflict"})

    # Miguel's identity extraction (W3-05) + Tobías's document state (W3-07).
    extracted_identity = storage.extract_identity_fields(data, content_type)
    if extracted_identity:
        storage.attach_case_identity(case_id, extracted_identity)

    storage.append_case_document_state(
        case_id,
        document_name,
        status="stored",
        outcome="accepted",
        notification="Document stored successfully and case flow continues.",
        metadata={"target_name": target_name, "content_type": content_type},
    )
    return {
        "status": "stored",
        "blob": target_name,
        "document_name": document_name,
        "outcome": "accepted",
        "extracted_identity": extracted_identity,
    }


@app.get("/cases/{case_id}/documents")
def list_case_documents(case_id: str):
    """Analyst-facing state of every document attempt for a case (W3-07)."""
    return {"documents": storage.list_case_documents(case_id)}


@app.get("/cases/{case_id}/documents/{document_name}/access-link")
def document_access_link(
    case_id: str,
    document_name: str,
    minutes: int = 15,
    _auth: None = Depends(_require_analyst_access),
):
    try:
        if not storage.document_exists(case_id, document_name):
            raise HTTPException(404, detail={"error": "document_not_found"})
        return storage.issue_document_access_link(case_id, document_name, minutes=minutes)
    except ValueError as exc:
        raise HTTPException(400, detail={"error": "invalid_access_link_request", "reason": str(exc)})
