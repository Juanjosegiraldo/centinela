import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from api.app import events, storage


class EventPublishingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-events-", dir="/tmp")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        os.environ.pop("SERVICEBUS_FQDN", None)
        os.environ.pop("SBUS_TOPIC", None)
        importlib.reload(storage)
        importlib.reload(events)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_publish_transaction_received_writes_local_event_log(self) -> None:
        record = {
            "transaction_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "account_id": "acct-1234",
            "amount_minor": 12500,
            "currency": "USD",
            "occurred_at": "2026-07-29T10:00:00+00:00",
            "location": {"lat": 4.7110, "lon": -74.0721},
            "merchant_id": "merchant-safe",
            "merchant_category": "retail",
            "received_at": "2026-07-29T10:01:00+00:00",
        }

        events.publish_transaction_received(record)

        event_log = Path(self.tempdir.name) / "topic-messages.jsonl"
        self.assertTrue(event_log.exists())

        line = event_log.read_text(encoding="utf-8").strip()
        event = json.loads(line)
        self.assertEqual(event["event_type"], "transaction.received")
        self.assertEqual(event["record"], record)
        self.assertEqual(event["topic"], "transaction-received")
        self.assertIn("published_at", event)
