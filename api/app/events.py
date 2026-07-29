"""Event publishing for the ingestion flow."""

import json
import os
from datetime import datetime, timezone
from functools import lru_cache

try:
    from azure.identity import DefaultAzureCredential
    from azure.servicebus import ServiceBusClient, ServiceBusMessage
except ImportError:  # pragma: no cover - local/dev fallback
    DefaultAzureCredential = None
    ServiceBusClient = None
    ServiceBusMessage = None

from . import storage

SERVICEBUS_FQDN = os.environ.get("SERVICEBUS_FQDN")
SERVICEBUS_TOPIC = os.environ.get("SBUS_TOPIC", "transaction-received")


@lru_cache(maxsize=1)
def _credential():
    if DefaultAzureCredential is None:
        return None
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _servicebus_client():
    if ServiceBusClient is None or SERVICEBUS_FQDN is None:
        return None
    return ServiceBusClient(fully_qualified_namespace=SERVICEBUS_FQDN, credential=_credential())


def _local_event_path():
    return storage._local_path("topic-messages.jsonl")


def publish_transaction_received(record: dict) -> None:
    event = {
        "event_type": "transaction.received",
        "record": record,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "topic": SERVICEBUS_TOPIC,
    }

    if _servicebus_client() is not None and ServiceBusMessage is not None:
        message = ServiceBusMessage(json.dumps(event), content_type="application/json")
        with _servicebus_client().get_topic_sender(topic_name=SERVICEBUS_TOPIC) as sender:
            sender.send_messages(message)
        return

    path = _local_event_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
