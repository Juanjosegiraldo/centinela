import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from api.app import storage
import engine.function_app as function_app

process_transaction_event = function_app.process_transaction_event


class ScoringEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-test-")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        os.environ.pop("STORAGE_ACCOUNT_URL", None)
        os.environ.pop("QUEUE_ACCOUNT_URL", None)
        os.environ.pop("SCORING_THRESHOLD", None)

    def tearDown(self) -> None:
        try:
            self.tempdir.cleanup()
        except OSError:
            pass
        importlib.reload(function_app)
        global process_transaction_event
        process_transaction_event = function_app.process_transaction_event

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

        os.environ["SCORING_THRESHOLD"] = "50"
        result = process_transaction_event(transaction_id)

        self.assertTrue(result["scored"])
        self.assertEqual(result["transaction_id"], transaction_id)
        # atypical_amount (30) + risky_merchant (25) = 55, weighted 0–100.
        self.assertEqual(result["score"], 55)
        self.assertEqual(
            {rule["id"] for rule in result["rules_triggered"]},
            {"atypical_amount", "risky_merchant"},
        )
        self.assertIn("rules", result)
        self.assertIn("scored_at", result)
        self.assertIn("case_enqueued", result)

        updated = storage.load_transaction(transaction_id)
        self.assertEqual(updated["score"], result["score"])
        # 55 >= threshold 50 => a case is opened.
        self.assertTrue(updated["case_enqueued"])

        flagged_cases = Path(self.tempdir.name) / "flagged-cases.jsonl"
        self.assertTrue(flagged_cases.exists())
        self.assertIn(transaction_id, flagged_cases.read_text(encoding="utf-8"))

    def test_scoring_emits_telemetry_for_transaction(self) -> None:
        payload = {
            "transaction_id": "tx-telemetry",
            "account_id": "acct-telemetry",
            "amount_minor": 1000000,
            "occurred_at": "2026-01-01T00:00:00Z",
            "location": {"lat": 0.0, "lon": 0.0},
            "merchant_id": "risk-merchant",
            "merchant_category": "travel",
        }

        # Telemetry is emitted through logging (sink = Application Insights in
        # the cloud); capture the structured line instead of reading a file.
        with self.assertLogs(level="INFO") as captured:
            function_app.handle_transaction(payload)

        telemetry = None
        for line in captured.output:
            _, _, message = line.partition(":root:")
            try:
                parsed = json.loads(message)
            except (json.JSONDecodeError, ValueError):
                continue
            if parsed.get("telemetry") == "scoring" and parsed.get("transaction_id") == "tx-telemetry":
                telemetry = parsed
                break
        self.assertIsNotNone(telemetry)
        self.assertIn("duration_ms", telemetry)
        self.assertIn(telemetry["outcome"], {"case_opened", "scored_only"})

    def test_detects_rule_details_and_threshold_configuration(self) -> None:
        previous_id = "22222222-3333-4444-5555-666666666666"
        previous_payload = {
            "transaction_id": previous_id,
            "account_id": "acct-002",
            "amount_minor": 50000,
            "currency": "USD",
            "occurred_at": "2026-07-27T09:55:00+00:00",
            "location": {"lat": 40.7306, "lon": -73.9352},
            "merchant_id": "merchant-safe",
            "merchant_category": "retail",
            "received_at": "2026-07-27T09:56:00+00:00",
        }
        storage.persist_transaction(previous_id, json.dumps(previous_payload))

        transaction_id = "33333333-4444-5555-6666-777777777777"
        payload = {
            "transaction_id": transaction_id,
            "account_id": "acct-002",
            "amount_minor": 250000,
            "currency": "USD",
            "occurred_at": "2026-07-27T10:00:00+00:00",
            "location": {"lat": 12.9716, "lon": 77.5946},
            "merchant_id": "merchant-risk",
            "merchant_category": "travel",
            "received_at": "2026-07-27T10:01:00+00:00",
        }
        storage.persist_transaction(transaction_id, json.dumps(payload))

        # Weighted score here = geo_impossible(60) + atypical_amount(30)
        # + risky_merchant(25) + velocity(40) = 155. A threshold above it
        # keeps the case closed; the threshold is configuration, not code.
        os.environ["SCORING_THRESHOLD"] = "200"
        result = process_transaction_event(transaction_id)

        triggered_ids = {rule["id"] for rule in result["rules"] if rule["triggered"]}
        self.assertIn("atypical_amount", triggered_ids)
        self.assertIn("geo_impossible", triggered_ids)
        self.assertIn("risky_merchant", triggered_ids)
        self.assertFalse(result["case_enqueued"])

        for rule in result["rules"]:
            if rule["triggered"]:
                self.assertIn("observed", rule)

        os.environ["SCORING_THRESHOLD"] = "50"
        result = process_transaction_event(transaction_id)
        self.assertTrue(result["case_enqueued"])


if __name__ == "__main__":
    unittest.main()
