"""
Persistence layer (repository). The only module that talks to Azure Storage.
Authentication: DefaultAzureCredential -> the Web App's managed identity.
No keys or connection strings exist in code or configuration.
"""
import json
import os
import re
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

try:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
except ImportError:  # pragma: no cover - local/dev fallback
    DocumentIntelligenceClient = None
    AzureKeyCredential = None

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


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_via_document_intelligence(data: bytes) -> dict:
    endpoint = os.environ.get("DOCUMENTINTELLIGENCE_ENDPOINT")
    key = os.environ.get("DOCUMENTINTELLIGENCE_KEY")
    if not endpoint or (not key and DefaultAzureCredential is None):
        return {}
    if DocumentIntelligenceClient is None:
        return {}

    try:
        if key and AzureKeyCredential is not None:
            client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        else:
            client = DocumentIntelligenceClient(endpoint=endpoint, credential=DefaultAzureCredential())
        poller = client.begin_analyze_document(
            "prebuilt-idDocument",
            analyze_request=data,
            content_type="application/octet-stream",
        )
        result = poller.result()
    except Exception:
        return {}

    def _read_field(names: list[str]):
        for name in names:
            field = getattr(result, "fields", {}).get(name)
            if field is None:
                continue
            value = getattr(field, "value_string", None)
            if value is None:
                value = getattr(field, "value_date", None)
            if value is None:
                value = getattr(field, "content", None)
            if value is not None:
                return str(value)
        return None

    name = _read_field(["Name", "FullName", "GivenNames"])
    identification_number = _read_field(["DocumentNumber", "IdentificationNumber", "IDNumber", "PassportNumber"])
    birth_date = _read_field(["DateOfBirth", "BirthDate"])
    issue_date = _read_field(["IssueDate", "DateOfIssue"])

    metadata = {}
    if name:
        metadata["name"] = name
    if identification_number:
        metadata["identification_number"] = identification_number
    if birth_date:
        metadata["date_of_birth"] = _normalize_date(birth_date) or birth_date
    if issue_date:
        metadata["issue_date"] = _normalize_date(issue_date) or issue_date
    if metadata:
        metadata["source"] = "document-intelligence"
    return metadata


def extract_identity_fields(data: bytes, content_type: str | None = None) -> dict:
    """Extract the most relevant identity fields from uploaded content.

    The implementation uses a deterministic heuristic on text content so the
    feature is testable locally. In Azure, the same function can be extended to
    call Document Intelligence F0 when the endpoint and credentials are present.
    """
    azure_result = _extract_via_document_intelligence(data)
    if azure_result:
        return azure_result

    text = data.decode("utf-8", errors="ignore")
    if not text.strip():
        return {}

    def _find(patterns: list[str]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    name = _find([
        r"\bname\s*[:\-]\s*(.+)",
        r"\bfull\s+name\s*[:\-]\s*(.+)",
    ])
    identification_number = _find([
        r"\bidentification\s+number\s*[:\-]\s*(.+)",
        r"\bid\s*number\s*[:\-]\s*(.+)",
        r"\bpassport\s*[:\-]\s*(.+)",
    ])
    date_of_birth = _normalize_date(_find([
        r"\bdate\s+of\s+birth\s*[:\-]\s*(.+)",
        r"\bbirth\s+date\s*[:\-]\s*(.+)",
    ]))
    issue_date = _normalize_date(_find([
        r"\bissue\s+date\s*[:\-]\s*(.+)",
        r"\bissued\s+on\s*[:\-]\s*(.+)",
    ]))

    metadata = {}
    if name:
        metadata["name"] = name
    if identification_number:
        metadata["identification_number"] = identification_number
    if date_of_birth:
        metadata["date_of_birth"] = date_of_birth
    if issue_date:
        metadata["issue_date"] = issue_date
    metadata["source"] = "heuristic"
    return metadata


def attach_case_identity(case_id: str, metadata: dict) -> dict:
    payload = {
        "case_id": case_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **metadata,
    }
    blob_name = f"case-{case_id}.json"
    if _blobs() is not None:
        _blobs().get_blob_client(DOCS_CONTAINER, blob_name).upload_blob(
            json.dumps(payload),
            overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )
        return payload

    _local_path(blob_name).write_text(json.dumps(payload), encoding="utf-8")
    return payload


def load_case_identity(case_id: str) -> dict:
    blob_name = f"case-{case_id}.json"
    if _blobs() is not None:
        blob = _blobs().get_blob_client(DOCS_CONTAINER, blob_name)
        if not blob.exists():
            return {}
        return json.loads(blob.download_blob().readall())

    path = _local_path(blob_name)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


# Document state (W3-07): one JSON blob per document attempt under
# case-state/{case_id}/. Blob-backed so the state survives restarts and is
# shared across workers (a local file would be ephemeral and per-instance in
# the cloud); local fallback keeps tests hermetic.
def _case_state_prefix(case_id: str) -> str:
    return f"case-state/{case_id}/"


def append_case_document_state(case_id: str, document_name: str, status: str, outcome: str, notification: str, metadata: dict | None = None) -> None:
    record = {
        "case_id": case_id,
        "document_name": document_name,
        "status": status,
        "outcome": outcome,
        "notification": notification,
        "metadata": metadata or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    blob_name = f"{_case_state_prefix(case_id)}{document_name}.json"
    if _blobs() is not None:
        _blobs().get_blob_client(DOCS_CONTAINER, blob_name).upload_blob(
            json.dumps(record), overwrite=True,
            content_settings=ContentSettings(content_type="application/json"),
        )
        return
    path = _local_path(blob_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")


def list_case_documents(case_id: str) -> list[dict]:
    if _blobs() is not None:
        container = _blobs().get_container_client(DOCS_CONTAINER)
        rows = []
        for blob in container.list_blobs(name_starts_with=_case_state_prefix(case_id)):
            data = container.get_blob_client(blob.name).download_blob().readall()
            rows.append(json.loads(data))
        return sorted(rows, key=lambda r: r.get("updated_at", ""))
    root = _local_path(_case_state_prefix(case_id))
    if not root.exists():
        return []
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*.json"))]
    return sorted(rows, key=lambda r: r.get("updated_at", ""))


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
