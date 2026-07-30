import importlib
import os
import tempfile
import unittest
from pathlib import Path

from api.app import storage


class IdentityDocumentExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="centinela-test-")
        os.environ["CENTINELA_LOCAL_STORAGE"] = self.tempdir.name
        importlib.reload(storage)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_extracts_identity_fields_from_text_content(self) -> None:
        payload = b"NAME: Maria Elena Ruiz\nIDENTIFICATION NUMBER: 12345678\nDATE OF BIRTH: 03/04/1990\nISSUE DATE: 01/10/2020"
        metadata = storage.extract_identity_fields(payload, "text/plain")

        self.assertEqual(metadata["name"], "Maria Elena Ruiz")
        self.assertEqual(metadata["identification_number"], "12345678")
        self.assertEqual(metadata["date_of_birth"], "1990-04-03")
        self.assertEqual(metadata["issue_date"], "2020-10-01")

    def test_upload_document_persists_extracted_identity_metadata(self) -> None:
        metadata = storage.extract_identity_fields(
            b"NAME: Maria Elena Ruiz\nIDENTIFICATION NUMBER: 12345678\nDATE OF BIRTH: 03/04/1990\nISSUE DATE: 01/10/2020",
            "text/plain",
        )
        storage.attach_case_identity("case-001", metadata)

        metadata_path = Path(self.tempdir.name) / "case-case-001.json"
        self.assertTrue(metadata_path.exists())
        persisted = metadata_path.read_text(encoding="utf-8")
        self.assertIn("Maria Elena Ruiz", persisted)


if __name__ == "__main__":
    unittest.main()
