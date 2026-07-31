from azure.storage.queue import QueueClient
from azure.identity import DefaultAzureCredential
import os

def main():
    account_url = os.environ.get("QUEUE_ACCOUNT_URL")
    queue_name = os.environ.get("QUEUE_NAME","q-incoming-transactions")
    if not account_url:
        raise SystemExit("QUEUE_ACCOUNT_URL not set")
    q = QueueClient(account_url=account_url, queue_name=queue_name, credential=DefaultAzureCredential())
    props = q.get_queue_properties()
    print(props.approximate_messages_count)

if __name__ == '__main__':
    main()
