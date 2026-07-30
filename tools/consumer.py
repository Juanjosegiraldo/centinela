"""Simple case consumer for verification.
Reads messages from the configured queue, writes a small JSON blob per
`transaction_id` into container `processed-transactions` with `processed_at`.
Run in a separate terminal; stop with Ctrl+C to simulate consumer downtime.
"""
import os, time, json
from datetime import datetime, timezone
from azure.identity import DefaultAzureCredential
from azure.storage.queue import QueueClient
from azure.storage.blob import BlobServiceClient, ContentSettings

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def main():
    account_url = os.environ.get("QUEUE_ACCOUNT_URL")
    queue_name = os.environ.get("QUEUE_NAME","q-incoming-transactions")
    blob_url = os.environ.get("STORAGE_ACCOUNT_URL")
    if not account_url or not blob_url:
        raise SystemExit("QUEUE_ACCOUNT_URL and STORAGE_ACCOUNT_URL must be set")

    # Prefer connection strings (Azurite/local) when provided, otherwise use
    # DefaultAzureCredential with the account URLs.
    queue_conn = os.environ.get("AZURE_QUEUE_CONNECTION_STRING")
    blob_conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if queue_conn:
        q = QueueClient.from_connection_string(conn_str=queue_conn, queue_name=queue_name)
    else:
        cred = DefaultAzureCredential()
        q = QueueClient(account_url=account_url, queue_name=queue_name, credential=cred)

    if blob_conn:
        svc = BlobServiceClient.from_connection_string(blob_conn)
    else:
        cred = DefaultAzureCredential()
        svc = BlobServiceClient(account_url=blob_url, credential=cred)
    container = os.environ.get("PROCESSED_CONTAINER","processed-transactions")
    try:
        svc.create_container(container)
    except Exception:
        pass

    print("Consumer started, polling queue... (Ctrl+C to stop)")
    while True:
        messages = q.receive_messages(messages_per_page=5, visibility_timeout=30)
        any_msg = False
        for msg in messages:
            any_msg = True
            try:
                txid = msg.content
                record = {"transaction_id": txid, "processed_at": now_iso()}
                blob_name = f"{txid}.json"
                svc.get_blob_client(container, blob_name).upload_blob(json.dumps(record), overwrite=True,
                                                                       content_settings=ContentSettings(content_type="application/json"))
                try:
                    # Received message object differs by SDK; prefer explicit delete by id/pop_receipt
                    q.delete_message(msg.id, msg.pop_receipt)
                except Exception:
                    try:
                        q.delete_message(msg)
                    except Exception:
                        print("Warning: failed to delete message (it may reappear)")
                print(f"Processed {txid}")
            except Exception as e:
                print(f"Failed processing message: {e}")
        if not any_msg:
            time.sleep(1)

if __name__ == '__main__':
    main()
