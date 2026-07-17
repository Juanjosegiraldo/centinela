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

STORAGE_ACCOUNT_URL = os.environ["STORAGE_ACCOUNT_URL"]
QUEUE_ACCOUNT_URL = os.environ["QUEUE_ACCOUNT_URL"]
TX_CONTAINER = os.environ.get("TX_CONTAINER", "raw-transactions")
DOCS_CONTAINER = os.environ.get("DOCS_CONTAINER", "verification-docs")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "q-incoming-transactions")


@lru_cache(maxsize=1)
def _credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _blobs() -> BlobServiceClient:
    return BlobServiceClient(account_url=STORAGE_ACCOUNT_URL, credential=_credential())


def persist_transaction(transaction_id: str, payload_json: str) -> str:
    """Persist the raw transaction. Name = id => idempotent retries."""
    blob_name = f"{transaction_id}.json"
    _blobs().get_blob_client(TX_CONTAINER, blob_name).upload_blob(
        payload_json, overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    return blob_name


def store_document(target_name: str, data: bytes, content_type: str) -> str:
    _blobs().get_blob_client(DOCS_CONTAINER, target_name).upload_blob(
        data, overwrite=False,
        content_settings=ContentSettings(content_type=content_type),
    )
    return target_name


@lru_cache(maxsize=1)
def queue() -> QueueClient:
    return QueueClient(account_url=QUEUE_ACCOUNT_URL, queue_name=QUEUE_NAME,
                       credential=_credential())
