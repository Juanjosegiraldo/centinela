"""Event publishing for the ingestion flow."""

from . import storage


def publish_transaction_received(transaction_id: str) -> None:
    storage.enqueue_transaction(transaction_id)
