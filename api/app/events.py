"""
INSERTION POINT — Week 2 (requirement 2.9, "messaging preparation").

Today `publish_transaction_received` does nothing. In Week 2 its body will
publish the event (e.g. write the message to the queue / Service Bus) WITHOUT
touching the endpoint: the endpoint flow already calls it after persisting.
"""


def publish_transaction_received(transaction_id: str) -> None:
    # Week 2: enqueue/publish the "transaction_received" event here.
    return None
