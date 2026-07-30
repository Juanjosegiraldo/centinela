import os
import tempfile
import unittest
from base64 import b64encode
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.app.auth import principal_roles, require_analyst_access
from api.app import storage
from api.app.main import app


class DocumentAccessLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-docs-")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        os.environ.pop("STORAGE_ACCOUNT_URL", None)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_document_blob_name_is_case_linked(self) -> None:
        blob_name = storage.document_blob_name("case-123", "abc123.pdf")
        self.assertEqual(blob_name, "case-123/abc123.pdf")

    def test_issue_document_access_link_local_fallback(self) -> None:
        blob_path = Path(self.tempdir.name) / "case-123" / "abc123.pdf"
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(b"%PDF-1.4 test")

        link = storage.issue_document_access_link("case-123", "abc123.pdf", minutes=5)

        self.assertEqual(link["blob"], "case-123/abc123.pdf")
        self.assertEqual(link["mechanism"], "local-fallback")
        self.assertTrue(link["url"].startswith("file:"))
        self.assertIn("expires_at", link)

    def test_document_name_rejects_nested_paths(self) -> None:
        with self.assertRaises(ValueError):
            storage.document_blob_name("case-123", "../escape.pdf")

    def test_principal_roles_parse_analyst_role(self) -> None:
        principal = {
            "auth_typ": "aad",
            "role_typ": "roles",
            "claims": [
                {"typ": "name", "val": "analyst@example.com"},
                {"typ": "roles", "val": "Analyst"},
                {"typ": "roles", "val": "Reader"},
            ],
        }
        header = b64encode(json.dumps(principal).encode("utf-8")).decode("ascii")
        self.assertEqual(principal_roles(header), {"Analyst", "Reader"})

    def test_corrupt_document_is_recorded_without_blocking_case_flow(self) -> None:
        header = self._analyst_header()
        response = self.client.post(
            "/cases/case-123/documents",
            files={"file": ("bad.bin", b"\x00\x01\x02", "application/octet-stream")},
            headers={"x-ms-client-principal": header},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "rejected")
        self.assertEqual(body["outcome"], "unsupported_format")
        self.assertIn("notification", body)

        list_response = self.client.get(
            "/cases/case-123/documents",
            headers={"x-ms-client-principal": header},
        )
        self.assertEqual(list_response.status_code, 200)
        documents = list_response.json()["documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["status"], "rejected")
        self.assertEqual(documents[0]["outcome"], "unsupported_format")

    def test_require_analyst_access_rejects_other_roles(self) -> None:
        principal = {
            "auth_typ": "aad",
            "role_typ": "roles",
            "claims": [{"typ": "roles", "val": "Auditor"}],
        }
        header = b64encode(json.dumps(principal).encode("utf-8")).decode("ascii")
        with self.assertRaises(PermissionError):
            require_analyst_access(header)

    def _analyst_header(self) -> str:
        principal = {
            "auth_typ": "aad",
            "role_typ": "roles",
            "claims": [{"typ": "roles", "val": "Analyst"}],
        }
        return b64encode(json.dumps(principal).encode("utf-8")).decode("ascii")


if __name__ == "__main__":
    unittest.main()
