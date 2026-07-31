import json
import os
import tempfile
import unittest
from pathlib import Path


class OpenCaseLocalFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-cases-")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        # No cloud config => open_case uses the local JSONL fallback.
        os.environ.pop("KEY_VAULT_URL", None)
        os.environ.pop("SERVICEBUS_FQDN", None)
        os.environ.pop("CENTINELA_ENABLE_CASE_EXPLAINER", None)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_open_case_records_locally_when_no_cloud_config(self) -> None:
        from engine import cases

        result = {"transaction_id": "abc-123", "score": 80}
        payload = {"account_id": "acct-9"}
        cases.open_case(result, payload)

        path = Path(self.tempdir.name) / "flagged-cases.jsonl"
        self.assertTrue(path.exists())
        record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["transaction_id"], "abc-123")
        self.assertEqual(record["account_id"], "acct-9")
        self.assertEqual(record["score"], 80)

    def test_generate_case_explanation_is_deterministic_and_rule_based(self) -> None:
        from engine import cases

        result = {
            "transaction_id": "abc-123",
            "score": 80,
            "rules_triggered": [
                {
                    "id": "velocity",
                    "observed": {
                        "occurred_at": "2026-01-01T00:00:00Z",
                        "previous_occured_at": "2025-12-31T23:59:59Z",
                        "window_seconds": 600,
                    },
                },
                {
                    "id": "geo_impossible",
                    "observed": {
                        "location": {"lat": 1.0, "lon": 2.0},
                        "previous_location": {"lat": 3.0, "lon": 4.0},
                        "distance_km": 5.0,
                    },
                },
            ],
        }

        explanation = cases.generate_case_explanation(result)
        expected = (
            "Case abc-123 was opened because the score reached the threshold. "
            "Rules fired: Rule velocity fired because the transaction occurred at 2026-01-01T00:00:00Z "
            "and the previous transaction in the 600-second window occurred at 2025-12-31T23:59:59Z. "
            "Rule geo_impossible fired because the observed location was 1.0, 2.0 and the previous location was 3.0, 4.0, "
            "with a distance of 5.0 km."
        )
        self.assertEqual(explanation, expected)

    def test_disabled_explainer_never_blocks_the_case(self) -> None:
        """W3-06 closure scenario: with the explainer stopped (kill-switch app
        setting), cases keep opening — the explanation is simply absent."""
        from engine import cases

        result = {
            "transaction_id": "abc-456",
            "score": 80,
            "rules_triggered": [
                {
                    "id": "risky_merchant",
                    "observed": {
                        "merchant_id": "merchant-risk",
                        "merchant_category": "travel",
                    },
                }
            ],
        }

        os.environ["CENTINELA_ENABLE_CASE_EXPLAINER"] = "false"
        self.assertIsNone(cases.build_explanation(result))

        # The case still opens while the explainer is stopped.
        cases.open_case({**result, "explanation": None}, {"account_id": "acct-10"})
        flagged = Path(self.tempdir.name) / "flagged-cases.jsonl"
        self.assertTrue(flagged.exists())
        record = json.loads(flagged.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["transaction_id"], "abc-456")
        self.assertIsNone(record["explanation"])

        # Re-enabled, the explanation is produced deterministically.
        os.environ["CENTINELA_ENABLE_CASE_EXPLAINER"] = "true"
        explanation = cases.build_explanation(result)
        self.assertIn("Rule risky_merchant fired", explanation)
        self.assertIn("merchant-risk", explanation)


if __name__ == "__main__":
    unittest.main()
