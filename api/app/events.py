"""
INSERTION POINT — Week 2 (requirement 2.9, "messaging preparation").

Today `publish_transaction_received` does nothing. In Week 2 its body will
publish the event (e.g. write the message to the queue / Service Bus) WITHOUT
touching the endpoint: the endpoint flow already calls it after persisting.
"""

from . import storage


def publish_transaction_received(transaction_id: str) -> None:
    # Week 2: enqueue/publish the "transaction_received" event here.
    # Implementation: write the transaction_id as a message to the configured
    # queue using the repository `storage.queue()` helper. This function MUST
    # NOT raise on failure because the API's correctness depends on the
    # persistence step; publishing is best-effort and must not break the API
    # flow (the endpoint already acknowledged after persisting).
    try:
        q = storage.queue()
        # Azure Queue expects str payloads. Keep the message small (id only).
        q.send_message(transaction_id)
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        # Do not propagate to the API path. Log to stderr for operator visibility.
        import sys
        print(f"events.publish_transaction_received: failed to enqueue {transaction_id}: {exc}", file=sys.stderr)
        return None
