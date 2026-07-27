"""
Persistence layer (repository). The only module that talks to Azure Storage.
Authentication: DefaultAzureCredential -> the Web App's managed identity.
No keys or connection strings exist in code or configuration.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

try:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient, ContentSettings
    from azure.storage.queue import QueueClient
except ImportError:  # pragma: no cover - local/dev fallback
    DefaultAzureCredential = None
    BlobServiceClient = None
    ContentSettings = None
    QueueClient = None

STORAGE_ACCOUNT_URL = os.environ.get("STORAGE_ACCOUNT_URL")
QUEUE_ACCOUNT_URL = os.environ.get("QUEUE_ACCOUNT_URL")
TX_CONTAINER = os.environ.get("TX_CONTAINER", "raw-transactions")
DOCS_CONTAINER = os.environ.get("DOCS_CONTAINER", "verification-docs")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "q-incoming-transactions")
LOCAL_STORAGE_ROOT = os.environ.get("CENTINELA_LOCAL_STORAGE")


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
    if LOCAL_STORAGE_ROOT:
        root = Path(LOCAL_STORAGE_ROOT)
    else:
        root = Path(__file__).resolve().parent.parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_path(name: str) -> Path:
    return _local_storage_dir() / name


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
