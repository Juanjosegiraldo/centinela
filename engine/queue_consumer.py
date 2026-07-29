import os

from api.app import storage
from engine.function_app import process_transaction_event


def process_incoming_transactions() -> list[dict]:
    results: list[dict] = []
    while True:
        message = storage.receive_next_transaction()
        if message is None:
            break
        results.append(process_transaction_event(message["transaction_id"]))
    return results
