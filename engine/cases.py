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
import threading
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
_EXPLAINER_ENABLED = True
_EXPLAINER_THREAD = None
_EXPLAINER_LOCK = threading.Lock()


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


def _local_storage_root() -> Path:
    root_env = os.environ.get("CENTINELA_LOCAL_STORAGE")
    return Path(root_env) if root_env else Path(__file__).resolve().parent.parent / "data"


def _record_local(body: dict) -> None:
    root = _local_storage_root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "flagged-cases.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body) + "\n")


def _append_jsonl(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _rule_observation_text(rule: dict) -> str:
    observed = rule.get("observed") or {}
    rule_id = rule.get("id")
    if rule_id == "velocity":
        occurred_at = observed.get("occurred_at")
        previous_occured_at = observed.get("previous_occured_at")
        window_seconds = observed.get("window_seconds")
        if occurred_at and previous_occured_at and window_seconds is not None:
            return (
                f"the transaction occurred at {occurred_at} and the previous transaction in the {window_seconds}-second "
                f"window occurred at {previous_occured_at}"
            )
        return "the observed time values were recorded"

    if rule_id == "geo_impossible":
        location = observed.get("location") or {}
        previous_location = observed.get("previous_location") or {}
        distance_km = observed.get("distance_km")
        lat = location.get("lat")
        lon = location.get("lon")
        prev_lat = previous_location.get("lat")
        prev_lon = previous_location.get("lon")
        if lat is not None and lon is not None and prev_lat is not None and prev_lon is not None and distance_km is not None:
            return (
                f"the observed location was {lat}, {lon} and the previous location was {prev_lat}, {prev_lon}, "
                f"with a distance of {distance_km} km"
            )
        return "location observations were recorded"

    if rule_id == "risky_merchant":
        merchant_id = observed.get("merchant_id")
        merchant_category = observed.get("merchant_category")
        if merchant_id and merchant_category:
            return f"the merchant id was {merchant_id} and the merchant category was {merchant_category}"
        if merchant_id:
            return f"the merchant id was {merchant_id}"
        if merchant_category:
            return f"the merchant category was {merchant_category}"
        return "merchant observations were recorded"

    if rule_id == "atypical_amount":
        amount_minor = observed.get("amount_minor")
        if amount_minor is not None:
            return f"the observed amount was {amount_minor}"
        return "the observed amount was recorded"

    return "the observed values were recorded"


def generate_case_explanation(result: dict) -> str:
    """Create a deterministic, template-based explanation for a flagged case."""
    transaction_id = str(result.get("transaction_id", "unknown"))
    rules = result.get("rules_triggered") or []
    clauses = []
    for rule in rules:
        rule_id = rule.get("id")
        observation_text = _rule_observation_text(rule)
        clauses.append(f"Rule {rule_id} fired because {observation_text}.")

    if clauses:
        body = " ".join(clauses)
        return f"Case {transaction_id} was opened because the score reached the threshold. Rules fired: {body}"
    return f"Case {transaction_id} was opened because the score reached the threshold."


def _explainer_enabled() -> bool:
    return os.environ.get("CENTINELA_ENABLE_CASE_EXPLAINER", "true").lower() != "false"


def stop_explainer() -> None:
    global _EXPLAINER_ENABLED
    _EXPLAINER_ENABLED = False


def process_pending_explanations() -> None:
    root = _local_storage_root()
    pending_path = root / "pending-case-explanations.jsonl"
    explanations_path = root / "case-explanations.jsonl"
    pending_rows = _read_jsonl(pending_path)
    if not pending_rows:
        return

    processed = []
    for row in pending_rows:
        explanation = generate_case_explanation(row.get("result") or row)
        processed.append({
            "transaction_id": row.get("transaction_id") or (row.get("result") or {}).get("transaction_id"),
            "explanation": explanation,
        })

    existing = _read_jsonl(explanations_path)
    existing.extend(processed)
    _write_jsonl(explanations_path, existing)
    _write_jsonl(pending_path, [])


def _process_pending_explanations_async() -> None:
    global _EXPLAINER_THREAD
    if not _explainer_enabled():
        return
    with _EXPLAINER_LOCK:
        if _EXPLAINER_THREAD is not None and _EXPLAINER_THREAD.is_alive():
            return
        _EXPLAINER_THREAD = threading.Thread(target=process_pending_explanations, daemon=True)
        _EXPLAINER_THREAD.start()


def _queue_pending_explanation(result: dict, payload: dict) -> None:
    root = _local_storage_root()
    root.mkdir(parents=True, exist_ok=True)
    pending_path = root / "pending-case-explanations.jsonl"
    _append_jsonl(pending_path, {
        "transaction_id": result.get("transaction_id"),
        "account_id": payload.get("account_id"),
        "result": result,
    })


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

    _queue_pending_explanation(result, payload)
    if _explainer_enabled():
        _process_pending_explanations_async()

    logging.info(
        "case opened for %s (sql=%s, queued=%s)",
        case["transaction_id"], wrote_sql, enqueued,
    )
