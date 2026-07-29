"""
Persistence layer (repository). The only module that talks to Azure Storage.
Authentication: DefaultAzureCredential -> the Web App's managed identity.
No keys or connection strings exist in code or configuration.
"""
import json
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta

try:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import (
        BlobServiceClient,
        BlobSasPermissions,
        ContentSettings,
        generate_blob_sas,
    )
    from azure.storage.queue import QueueClient
except ImportError:  # pragma: no cover - local/dev fallback
    DefaultAzureCredential = None
    BlobServiceClient = None
    BlobSasPermissions = None
    ContentSettings = None
    generate_blob_sas = None
    QueueClient = None

STORAGE_ACCOUNT_URL = os.environ.get("STORAGE_ACCOUNT_URL")
QUEUE_ACCOUNT_URL = os.environ.get("QUEUE_ACCOUNT_URL")
TX_CONTAINER = os.environ.get("TX_CONTAINER", "raw-transactions")
DOCS_CONTAINER = os.environ.get("DOCS_CONTAINER", "verification-docs")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "q-incoming-transactions")
POISON_QUEUE_NAME = os.environ.get("POISON_QUEUE_NAME", "q-poison-transactions")
LOCAL_STORAGE_ROOT = os.environ.get("CENTINELA_LOCAL_STORAGE")
POISON_THRESHOLD = int(os.environ.get("POISON_THRESHOLD", "5"))


@lru_cache(maxsize=1)
def _credential():
    if DefaultAzureCredential is None:
        return None
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _blobs():
    if BlobServiceClient is None or STORAGE_ACCOUNT_URL is None:
        return None
    return BlobServiceClient(account_url=STORAGE_ACCOUNT_URL, credential=_credential())


def _local_storage_dir() -> Path:
    # Read the override at call time (not import time) so each test's
    # CENTINELA_LOCAL_STORAGE is honored and the local fallback stays hermetic.
    root_env = os.environ.get("CENTINELA_LOCAL_STORAGE")
    if root_env:
        root = Path(root_env)
    else:
        root = Path(__file__).resolve().parent.parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_path(name: str) -> Path:
    return _local_storage_dir() / name


def document_blob_name(case_id: str, document_name: str) -> str:
    if not case_id or not document_name:
        raise ValueError("case_id and document_name are required")
    if "/" in document_name or "\\" in document_name:
        raise ValueError("document_name must be a single path segment")
    return f"{case_id}/{document_name}"


def _storage_account_name() -> str | None:
    if not STORAGE_ACCOUNT_URL:
        return None
    hostname = urlparse(STORAGE_ACCOUNT_URL).hostname or ""
    return hostname.split(".")[0] if hostname else None


def persist_transaction(transaction_id: str, payload_json: str) -> str:
    """Persist the raw transaction. Name = id => idempotent retries."""
    if _blobs() is not None:
        blob_name = f"{transaction_id}.json"
        _blobs().get_blob_client(TX_CONTAINER, blob_name).upload_blob(
            payload_json, overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )
        return blob_name

    blob_name = f"{transaction_id}.json"
    _local_path(blob_name).write_text(payload_json, encoding="utf-8")
    return blob_name


def load_transaction(transaction_id: str) -> dict:
    if _blobs() is not None:
        blob_name = f"{transaction_id}.json"
        blob = _blobs().get_blob_client(TX_CONTAINER, blob_name)
        if not blob.exists():
            return {}
        return json.loads(blob.download_blob().readall())

    blob_name = f"{transaction_id}.json"
    path = _local_path(blob_name)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_account_history(account_id: str) -> list[dict]:
    if _blobs() is not None:
        return []

    history = []
    for path in sorted(_local_storage_dir().glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("account_id") == account_id:
            history.append(payload)
    history.sort(key=lambda item: item.get("occurred_at", ""))
    return history


def store_document(target_name: str, data: bytes, content_type: str) -> str:
    if _blobs() is not None:
        _blobs().get_blob_client(DOCS_CONTAINER, target_name).upload_blob(
            data, overwrite=False,
            content_settings=ContentSettings(content_type=content_type),
        )
        return target_name

    path = _local_path(target_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return target_name


def document_exists(case_id: str, document_name: str) -> bool:
    blob_name = document_blob_name(case_id, document_name)
    if _blobs() is not None:
        return _blobs().get_blob_client(DOCS_CONTAINER, blob_name).exists()
    return _local_path(blob_name).exists()


def issue_document_access_link(case_id: str, document_name: str, minutes: int = 15) -> dict:
    if minutes < 1 or minutes > 60:
        raise ValueError("minutes must be between 1 and 60")

    blob_name = document_blob_name(case_id, document_name)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    if _blobs() is None or generate_blob_sas is None or BlobSasPermissions is None:
        return {
            "blob": blob_name,
            "url": _local_path(blob_name).resolve().as_uri(),
            "expires_at": expires_at.isoformat(),
            "mechanism": "local-fallback",
        }

    account_name = _storage_account_name()
    if account_name is None:
        raise RuntimeError("storage account URL is not configured")

    service_client = _blobs()
    start_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    delegation_key = service_client.get_user_delegation_key(start_at, expires_at)
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=DOCS_CONTAINER,
        blob_name=blob_name,
        user_delegation_key=delegation_key,
        permission=BlobSasPermissions(read=True),
        start=start_at,
        expiry=expires_at,
        protocol="https",
    )
    blob_url = service_client.get_blob_client(DOCS_CONTAINER, blob_name).url
    return {
        "blob": blob_name,
        "url": f"{blob_url}?{sas_token}",
        "expires_at": expires_at.isoformat(),
        "mechanism": "user-delegation-sas",
    }


@lru_cache(maxsize=1)
def queue():
    if QueueClient is None or QUEUE_ACCOUNT_URL is None:
        return None
    return QueueClient(account_url=QUEUE_ACCOUNT_URL, queue_name=QUEUE_NAME,
                       credential=_credential())


def enqueue_transaction(transaction_id: str) -> str:
    if queue() is not None:
        queue().send_message(transaction_id)
        return transaction_id

    queue_file = _local_path("queue-messages.jsonl")
    with queue_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"transaction_id": transaction_id}) + "\n")
    return transaction_id


def _poison_queue():
    if QueueClient is None or QUEUE_ACCOUNT_URL is None:
        return None
    return QueueClient(account_url=QUEUE_ACCOUNT_URL, queue_name=POISON_QUEUE_NAME,
                       credential=_credential())


def receive_next_transaction() -> dict | None:
    if queue() is not None:
        message = queue().receive_message(
            visibility_timeout=30,
            message_count=1,
        )
        if message is None:
            return None
        payload = {"transaction_id": message.content.decode("utf-8"), "message_id": message.id}
        return payload

    queue_file = _local_path("queue-messages.jsonl")
    if not queue_file.exists():
        return None
    with queue_file.open("r", encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]
    if not lines:
        return None
    payload = json.loads(lines[0])
    with queue_file.open("w", encoding="utf-8") as handle:
        for line in lines[1:]:
            handle.write(line + "\n")
    return {"transaction_id": payload["transaction_id"], "message_id": payload.get("transaction_id")}


def complete_transaction_message(message_id: str) -> None:
    if queue() is not None:
        queue().delete_message(message_id)
        return

    queue_file = _local_path("queue-messages.jsonl")
    if not queue_file.exists():
        return
    # local fallback is already removed when read; nothing else to do


def move_to_poison_queue(transaction_id: str, reason: str) -> None:
    if _poison_queue() is not None:
        _poison_queue().send_message(json.dumps({"transaction_id": transaction_id, "reason": reason}))
        return

    poison_file = _local_path("poison-queue.jsonl")
    with poison_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"transaction_id": transaction_id, "reason": reason}) + "\n")


def process_queue_message(handler, max_retries: int = POISON_THRESHOLD) -> dict | None:
    message = receive_next_transaction()
    if message is None:
        return None

    transaction_id = message["transaction_id"]
    message_id = message.get("message_id")
    try:
        result = handler(transaction_id)
        complete_transaction_message(message_id)
        return result
    except Exception as exc:
        if message_id is not None and message_id in {"poison"}:
            raise
        move_to_poison_queue(transaction_id, str(exc))
        complete_transaction_message(message_id)
        return {"transaction_id": transaction_id, "status": "poisoned", "reason": str(exc)}
