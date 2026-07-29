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


if __name__ == "__main__":
    unittest.main()
