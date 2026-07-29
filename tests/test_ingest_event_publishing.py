import importlib
import json
import os
import tempfile
import unittest

from api.app import events, storage

try:
    from api.app.main import ingest
except ImportError:  # pragma: no cover - local runtime without project deps
    ingest = None


@unittest.skipIf(ingest is None, "project runtime dependencies are not installed")
class IngestPublishingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-ingest-")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        os.environ.pop("SERVICEBUS_FQDN", None)
        os.environ.pop("SBUS_TOPIC", None)
        importlib.reload(storage)
        importlib.reload(events)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_ingest_persists_then_publishes_and_returns_202(self) -> None:
        class Tx:
            transaction_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

            def model_dump(self, mode: str = "json") -> dict:
                return {
                    "transaction_id": self.transaction_id,
                    "account_id": "acct-1234",
                    "amount_minor": 12500,
                    "currency": "USD",
                    "occurred_at": "2026-07-29T10:00:00+00:00",
                    "location": {"lat": 4.7110, "lon": -74.0721},
                    "merchant_id": "merchant-safe",
                    "merchant_category": "retail",
                }

        tx = Tx()

        response = ingest(tx)

        self.assertEqual(response["status"], "accepted")
        self.assertEqual(response["transaction_id"], str(tx.transaction_id))

        stored = storage.load_transaction(str(tx.transaction_id))
        self.assertEqual(stored["transaction_id"], str(tx.transaction_id))

        event_log = storage._local_path("topic-messages.jsonl")
        self.assertTrue(event_log.exists())
        event = json.loads(event_log.read_text(encoding="utf-8").strip())
        self.assertEqual(event["record"]["transaction_id"], str(tx.transaction_id))
        self.assertEqual(event["record"]["received_at"], stored["received_at"])