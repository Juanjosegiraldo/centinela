"""Engine data-access layer.

The scoring engine reads account history and persists scored transactions.
In Azure this is Cosmos DB (partition key ``/account_id``); locally it falls
back to JSON files so the rules can be exercised without any cloud dependency.

No keys or connection strings: Cosmos access uses managed identity
(DefaultAzureCredential). The Cosmos client itself is wired in Block 4 — the
seams below mark exactly where each operation plugs in.
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
    # Block 4 wires the Cosmos client here (managed identity). Until then the
    # engine runs on the local fallback so scoring is testable end to end.
    if CosmosClient is None or COSMOS_ENDPOINT is None:
        return None
    client = CosmosClient(COSMOS_ENDPOINT, credential=DefaultAzureCredential())
    return client.get_database_client(COSMOS_DB).get_container_client(COSMOS_CONTAINER)


def _local_storage_dir() -> Path:
    # Read the override at call time (not import time) so each test's
    # CENTINELA_LOCAL_STORAGE is honored and the local fallback stays hermetic.
    root_env = os.environ.get("CENTINELA_LOCAL_STORAGE")
    if root_env:
        root = Path(root_env)
    else:
        root = Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_path(name: str) -> Path:
    return _local_storage_dir() / name


def load_transaction(transaction_id: str) -> dict:
    """Fetch a single transaction by id (used by the by-id helper and tests)."""
    container = _container()
    if container is not None:
        items = list(container.query_items(
            query="SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": transaction_id}],
            enable_cross_partition_query=True,
        ))
        return items[0] if items else {}
    path = _local_path(f"{transaction_id}.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_account_history(account_id: str) -> list[dict]:
    """Recent transactions of an account, oldest first (velocity/geo rules)."""
    container = _container()
    if container is not None:
        items = container.query_items(
            query="SELECT * FROM c WHERE c.account_id = @account_id",
            parameters=[{"name": "@account_id", "value": account_id}],
            partition_key=account_id,
        )
        history = list(items)
        history.sort(key=lambda item: item.get("occurred_at", ""))
        return history
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


def persist_scored_transaction(transaction_id: str, payload: dict) -> str:
    """Persist the scored transaction (with rules_triggered) for audit/history."""
    container = _container()
    if container is not None:
        # `id` addresses the item; `account_id` is the partition key. TTL is
        # enforced by the container (90 days), not written per item.
        document = {**payload, "id": transaction_id}
        container.upsert_item(body=document)
        return transaction_id
    _local_path(f"{transaction_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return transaction_id
