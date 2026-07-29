"""
Persistence layer (repository). The only module that talks to Azure Storage.
Authentication: DefaultAzureCredential -> the Web App's managed identity.
No keys or connection strings exist in code or configuration.
"""
import os
from functools import lru_cache
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient


def _ensure_container(client, container_name: str) -> None:
    try:
        client.create_container(container_name)
    except Exception:
        pass


TX_CONTAINER = os.environ.get("TX_CONTAINER", "raw-transactions")
DOCS_CONTAINER = os.environ.get("DOCS_CONTAINER", "verification-docs")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "q-incoming-transactions")


@lru_cache(maxsize=1)
def _credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


def _local_emulator() -> bool:
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "") or os.environ.get("AZURE_QUEUE_CONNECTION_STRING", "")
    return "UseDevelopmentStorage=true" in conn.lower()


@lru_cache(maxsize=1)
def _blobs() -> BlobServiceClient:
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
    account_url = os.environ.get("STORAGE_ACCOUNT_URL", "") or "http://127.0.0.1:10000/devstoreaccount1"
    if conn or account_url.startswith(("http://127.0.0.1", "http://localhost")):
        kwargs = {}
        if _local_emulator() or account_url.startswith(("http://127.0.0.1", "http://localhost")):
            kwargs["api_version"] = "2023-11-03"
        if conn:
            return BlobServiceClient.from_connection_string(conn, **kwargs)
        return BlobServiceClient(account_url=account_url, credential=_credential(), **kwargs)
    if not account_url:
        raise RuntimeError("STORAGE_ACCOUNT_URL is not set")
    return BlobServiceClient(account_url=account_url, credential=_credential())


def persist_transaction(transaction_id: str, payload_json: str) -> str:
    """Persist the raw transaction. Name = id => idempotent retries."""
    blob_name = f"{transaction_id}.json"
    blobs = _blobs()
    _ensure_container(blobs, TX_CONTAINER)
    blobs.get_blob_client(TX_CONTAINER, blob_name).upload_blob(
        payload_json, overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    return blob_name


def store_document(target_name: str, data: bytes, content_type: str) -> str:
    blobs = _blobs()
    _ensure_container(blobs, DOCS_CONTAINER)
    blobs.get_blob_client(DOCS_CONTAINER, target_name).upload_blob(
        data, overwrite=False,
        content_settings=ContentSettings(content_type=content_type),
    )
    return target_name


@lru_cache(maxsize=1)
def queue() -> QueueClient:
    conn = os.environ.get("AZURE_QUEUE_CONNECTION_STRING", "")
    account_url = os.environ.get("QUEUE_ACCOUNT_URL", "") or "http://127.0.0.1:10001/devstoreaccount1"
    if conn or account_url.startswith(("http://127.0.0.1", "http://localhost")):
        kwargs = {}
        if _local_emulator() or account_url.startswith(("http://127.0.0.1", "http://localhost")):
            kwargs["api_version"] = "2023-11-03"
        if conn:
            q = QueueClient.from_connection_string(conn_str=conn, queue_name=QUEUE_NAME, **kwargs)
        else:
            q = QueueClient(account_url=account_url, queue_name=QUEUE_NAME,
                            credential=_credential(), **kwargs)
        try:
            q.create_queue()
        except Exception:
            pass
        return q
    if not account_url:
        raise RuntimeError("QUEUE_ACCOUNT_URL is not set")
    return QueueClient(account_url=account_url, queue_name=QUEUE_NAME,
                       credential=_credential())
