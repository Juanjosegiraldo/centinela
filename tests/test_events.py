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
        transaction_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        events.publish_transaction_received(transaction_id)

        event_log = Path(self.tempdir.name) / "topic-messages.jsonl"
        self.assertTrue(event_log.exists())

        line = event_log.read_text(encoding="utf-8").strip()
        event = json.loads(line)
        self.assertEqual(event["event_type"], "transaction.received")
        self.assertEqual(event["transaction_id"], transaction_id)
        self.assertEqual(event["topic"], "transaction-received")
        self.assertIn("published_at", event)
