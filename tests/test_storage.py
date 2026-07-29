import unittest
from unittest.mock import Mock, patch

from api.app import storage


class StorageTests(unittest.TestCase):
    def test_persist_transaction_creates_container_before_upload(self):
        blob_client = Mock()
        blob_service_client = Mock()
        blob_service_client.get_blob_client.return_value = blob_client

        with patch("api.app.storage._blobs", return_value=blob_service_client):
            storage.persist_transaction("tx-1", "{}")

        blob_service_client.create_container.assert_called_once_with(storage.TX_CONTAINER)
        blob_client.upload_blob.assert_called_once()


if __name__ == "__main__":
    unittest.main()
