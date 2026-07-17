"""
Capa de persistencia (repositorio). Único punto que habla con Azure Storage.
Autenticación: DefaultAzureCredential -> identidad gestionada de la Web App.
No hay claves ni cadenas de conexión en el código ni en la configuración.
"""
import os
from functools import lru_cache
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.queue import QueueClient

STORAGE_ACCOUNT_URL = os.environ["STORAGE_ACCOUNT_URL"]
QUEUE_ACCOUNT_URL = os.environ["QUEUE_ACCOUNT_URL"]
CONTAINER_TX = os.environ.get("CONTAINER_TX", "transacciones-crudas")
CONTAINER_DOCS = os.environ.get("CONTAINER_DOCS", "docs-verificacion")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "q-transacciones-entrantes")


@lru_cache(maxsize=1)
def _cred() -> DefaultAzureCredential:
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _blobs() -> BlobServiceClient:
    return BlobServiceClient(account_url=STORAGE_ACCOUNT_URL, credential=_cred())


def persistir_transaccion(transaction_id: str, payload_json: str) -> str:
    """Persiste la transacción cruda. Nombre = id => reintento idempotente."""
    nombre = f"{transaction_id}.json"
    _blobs().get_blob_client(CONTAINER_TX, nombre).upload_blob(
        payload_json, overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )
    return nombre


def guardar_documento(nombre_destino: str, data: bytes, content_type: str) -> str:
    _blobs().get_blob_client(CONTAINER_DOCS, nombre_destino).upload_blob(
        data, overwrite=False,
        content_settings=ContentSettings(content_type=content_type),
    )
    return nombre_destino


@lru_cache(maxsize=1)
def cola() -> QueueClient:
    return QueueClient(account_url=QUEUE_ACCOUNT_URL, queue_name=QUEUE_NAME,
                       credential=_cred())
