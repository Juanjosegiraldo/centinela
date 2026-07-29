import importlib
import json
import os
import tempfile
import unittest

from api.app import storage
import engine.function_app as function_app
from engine import queue_consumer


class QueueProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-queue-")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        os.environ.pop("STORAGE_ACCOUNT_URL", None)
        os.environ.pop("QUEUE_ACCOUNT_URL", None)
        importlib.reload(function_app)
        storage._local_path("queue-messages.jsonl").unlink(missing_ok=True)
        storage._local_path("poison-queue.jsonl").unlink(missing_ok=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_enqueue_and_process_message(self) -> None:
        transaction_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        payload = {
            "transaction_id": transaction_id,
            "account_id": "acct-queue",
            "amount_minor": 120000,
            "currency": "USD",
            "occurred_at": "2026-07-27T10:00:00+00:00",
            "location": {"lat": 40.7128, "lon": -74.0060},
            "merchant_id": "merchant-risk",
            "merchant_category": "travel",
            "received_at": "2026-07-27T10:01:00+00:00",
        }
        storage.persist_transaction(transaction_id, json.dumps(payload))
        storage.enqueue_transaction(transaction_id)

        result = queue_consumer.process_incoming_transactions()
        self.assertEqual(result[0]["transaction_id"], transaction_id)
        self.assertTrue(result[0]["scored"])

    def test_poison_policy_moves_failed_message(self) -> None:
        transaction_id = "11111111-2222-3333-4444-555555555555"
        storage.enqueue_transaction(transaction_id)

        def failing_handler(_transaction_id: str) -> dict:
            raise RuntimeError("boom")

        result = storage.process_queue_message(failing_handler)
        self.assertEqual(result["status"], "poisoned")
        self.assertIn("boom", result["reason"])


if __name__ == "__main__":
    unittest.main()
