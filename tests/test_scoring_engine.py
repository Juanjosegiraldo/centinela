import json
import os
import tempfile
import unittest

from api.app import storage
from engine.function_app import process_transaction_event


class ScoringEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-test-", dir="/tmp")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        os.environ.pop("STORAGE_ACCOUNT_URL", None)
        os.environ.pop("QUEUE_ACCOUNT_URL", None)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_process_transaction_event_persists_score_and_case_flag(self) -> None:
        transaction_id = "11111111-2222-3333-4444-555555555555"
        payload = {
            "transaction_id": transaction_id,
            "account_id": "acct-001",
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

        result = process_transaction_event(transaction_id)

        self.assertTrue(result["scored"])
        self.assertEqual(result["transaction_id"], transaction_id)
        self.assertGreaterEqual(result["score"], 1)
        self.assertIn("rules", result)
        self.assertIn("scored_at", result)
        self.assertIn("case_enqueued", result)

        updated = storage.load_transaction(transaction_id)
        self.assertEqual(updated["score"], result["score"])
        self.assertTrue(updated["case_enqueued"])


if __name__ == "__main__":
    unittest.main()
