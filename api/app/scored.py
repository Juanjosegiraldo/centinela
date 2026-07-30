"""Read-side access to scored transactions (Cosmos DB).

The scoring engine writes the scored transaction to Cosmos; this module lets the
API read it back so the console can poll for the real score after ingestion.
Managed identity only (no keys); local JSON fallback for dev/tests.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

try:
    from azure.identity import DefaultAzureCredential
    from azure.cosmos import CosmosClient
except ImportError:  # pragma: no cover - local/dev fallback
    DefaultAzureCredential = None
    CosmosClient = None

COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT")
COSMOS_DB = os.environ.get("COSMOS_DB", "centinela")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "transactions")
LOCAL_STORAGE_ROOT = os.environ.get("CENTINELA_LOCAL_STORAGE")


@lru_cache(maxsize=1)
def _container():
    if CosmosClient is None or COSMOS_ENDPOINT is None:
        return None
    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    return client.get_database_client(COSMOS_DB).get_container_client(COSMOS_CONTAINER)


def _local_path(name: str) -> Path:
    root = (
        Path(LOCAL_STORAGE_ROOT)
        if LOCAL_STORAGE_ROOT
        else Path(__file__).resolve().parent.parent.parent / "data"
    )
    return root / name


def get_scored_transaction(transaction_id: str) -> "dict | None":
    """Return the scored record for a transaction, or None if not scored yet.

    The engine only writes to Cosmos once it has scored the transaction, so a
    missing record means the analysis is still in flight.
    """
    container = _container()
    if container is not None:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": transaction_id}],
            enable_cross_partition_query=True,
        ))
        return items[0] if items else None

    path = _local_path(f"{transaction_id}.json")
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    # Local fallback stores raw + scored in the same file; treat unscored as None.
    return record if record.get("scored") else None
