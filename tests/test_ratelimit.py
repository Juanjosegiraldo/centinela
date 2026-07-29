import importlib
import os
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
    from api.app.main import app
    from api.app import ratelimit
except ImportError:  # pragma: no cover - project runtime deps not installed here
    TestClient = None
    app = None
    ratelimit = None


@unittest.skipIf(TestClient is None or app is None or ratelimit is None,
                 "project runtime dependencies are not installed")
class RateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-rate-", dir="/tmp")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        os.environ["RATE_LIMIT_PER_MINUTE"] = "2"
        os.environ["RATE_LIMIT_WINDOW_SECONDS"] = "60"
        importlib.reload(ratelimit)
        ratelimit.reset_state()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tempdir.cleanup()
        ratelimit.reset_state()

    def test_transactions_beyond_limit_return_429(self) -> None:
        payload = {
            "transaction_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "account_id": "acct-1234",
            "amount_minor": 12000,
            "currency": "USD",
            "occurred_at": "2026-07-29T10:00:00+00:00",
            "location": {"lat": 4.7110, "lon": -74.0721},
            "merchant_id": "merchant-safe",
            "merchant_category": "retail",
        }

        headers = {"x-forwarded-for": "203.0.113.10"}
        first = self.client.post("/transactions", json=payload, headers=headers)
        second = self.client.post("/transactions", json=payload, headers=headers)
        third = self.client.post("/transactions", json=payload, headers=headers)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"], "rate_limit_exceeded")