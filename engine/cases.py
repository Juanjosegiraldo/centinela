"""Case store + flagged-cases publishing for the scoring engine.

When a transaction's score reaches the threshold the engine opens a case row
in Azure SQL (``casesdb``) and enqueues it on the Service Bus ``flagged-cases``
queue for guaranteed downstream processing.

Auth (no secret in code or app settings):
- Azure SQL: the connection string (SQL auth) is read at runtime from Key Vault
  via managed identity. The secret lives only in Key Vault.
- Service Bus: managed identity (DefaultAzureCredential), no keys.

Locally (no drivers / no config) both operations fall back to a JSONL file so
the pipeline is exercisable without any cloud dependency.
"""
import json
import logging
import os
from functools import lru_cache
from pathlib import Path

try:
    from azure.identity import DefaultAzureCredential
except ImportError:  # pragma: no cover - local/dev fallback
    DefaultAzureCredential = None

try:
    from azure.keyvault.secrets import SecretClient
except ImportError:  # pragma: no cover - local/dev fallback
    SecretClient = None

try:
    import pyodbc
except ImportError:  # pragma: no cover - local/dev fallback
    pyodbc = None

try:
    from azure.servicebus import ServiceBusClient, ServiceBusMessage
except ImportError:  # pragma: no cover - local/dev fallback
    ServiceBusClient = None
    ServiceBusMessage = None

KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL")
SQL_CONNECTION_SECRET = os.environ.get("SQL_CONNECTION_SECRET", "sql-connection-string")
ODBC_DRIVER = os.environ.get("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
SERVICEBUS_FQDN = os.environ.get("SERVICEBUS_FQDN")
SBUS_QUEUE = os.environ.get("SBUS_QUEUE", "flagged-cases")

OPEN_STATE_ID = 1  # case_states: 1 = open (see docs/schema.sql)


@lru_cache(maxsize=1)
def _credential():
    if DefaultAzureCredential is None:
        return None
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _sql_connection_string() -> "str | None":
    if SecretClient is None or KEY_VAULT_URL is None or _credential() is None:
        return None
    client = SecretClient(vault_url=KEY_VAULT_URL, credential=_credential())
    return client.get_secret(SQL_CONNECTION_SECRET).value


def _with_driver(conn_str: str) -> str:
    # The Key Vault secret holds Server/Database/credentials but not the ODBC
    # driver; pyodbc needs it. The driver must be installed on the Function's
    # Linux worker (msodbcsql18) — documented as a deploy prerequisite.
    if "driver=" in conn_str.lower():
        return conn_str
    return f"Driver={{{ODBC_DRIVER}}};" + conn_str


def _open_case_sql(transaction_id: str, account_id: str, score: int) -> bool:
    conn_str = _sql_connection_string()
    if pyodbc is None or conn_str is None:
        return False
    # Azure SQL serverless auto-pauses; the first call after idle can fail for
    # ~30-60s with "database not available". The Functions host retries the
    # message, so we do not swallow that transient error here.
    with pyodbc.connect(_with_driver(conn_str)) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO cases (transaction_id, account_id, score, state_id) "
                "VALUES (?, ?, ?, ?)",
                transaction_id, account_id, int(score), OPEN_STATE_ID,
            )
            conn.commit()
        except pyodbc.IntegrityError:
            # uq_cases_transaction: a case already exists for this transaction.
            # One case per transaction is the intended invariant, so a duplicate
            # is success (idempotent), not a failure.
            conn.rollback()
    return True


def _enqueue_flagged_case(body: dict) -> bool:
    if ServiceBusClient is None or SERVICEBUS_FQDN is None or _credential() is None:
        return False
    client = ServiceBusClient(
        fully_qualified_namespace=SERVICEBUS_FQDN, credential=_credential()
    )
    with client:
        sender = client.get_queue_sender(queue_name=SBUS_QUEUE)
        with sender:
            sender.send_messages(ServiceBusMessage(json.dumps(body)))
    return True


def _record_local(body: dict) -> None:
    root_env = os.environ.get("CENTINELA_LOCAL_STORAGE")
    root = Path(root_env) if root_env else Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    with (root / "flagged-cases.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body) + "\n")


def open_case(result: dict, payload: dict) -> None:
    """Open a case for a flagged transaction: SQL row + flagged-cases enqueue.

    Falls back to a local JSONL record when cloud drivers/config are absent, so
    the flow is exercisable in tests and offline demos.
    """
    case = {
        "transaction_id": result["transaction_id"],
        "account_id": payload.get("account_id"),
        "score": result["score"],
    }

    wrote_sql = _open_case_sql(case["transaction_id"], case["account_id"], case["score"])
    enqueued = _enqueue_flagged_case(case)

    if not wrote_sql and not enqueued:
        _record_local(case)

    logging.info(
        "case opened for %s (sql=%s, queued=%s)",
        case["transaction_id"], wrote_sql, enqueued,
    )
