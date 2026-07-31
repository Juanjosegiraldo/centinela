from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
import os, json

def read_blob(container, name):
    svc = BlobServiceClient(account_url=os.environ.get("STORAGE_ACCOUNT_URL"), credential=DefaultAzureCredential())
    b = svc.get_blob_client(container, name)
    data = b.download_blob().readall()
    return json.loads(data.decode())

if __name__ == '__main__':
    import sys
    if len(sys.argv)!=3:
        print("usage: fetch_persisted_records.py <container> <blob_name>")
        raise SystemExit(2)
    cont, name = sys.argv[1], sys.argv[2]
    print(json.dumps(read_blob(cont, name), indent=2))
