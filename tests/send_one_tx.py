import os
import requests
import uuid

os.environ['AZURE_STORAGE_CONNECTION_STRING'] = 'UseDevelopmentStorage=true'
os.environ['AZURE_QUEUE_CONNECTION_STRING'] = 'UseDevelopmentStorage=true'
os.environ['STORAGE_ACCOUNT_URL'] = 'http://127.0.0.1:10000/devstoreaccount1'
os.environ['QUEUE_ACCOUNT_URL'] = 'http://127.0.0.1:10001/devstoreaccount1'

tx = {
    'transaction_id': str(uuid.uuid4()),
    'account_id': 'acct-01',
    'amount_minor': 100,
    'currency': 'USD',
    'occurred_at': '2026-07-27T22:00:00+00:00',
    'location': {'lat': 0.0, 'lon': 0.0},
    'merchant_id': 'm-1',
    'merchant_category': 'general',
}
r = requests.post('http://127.0.0.1:8000/transactions', json=tx, timeout=10)
print(r.status_code)
print(r.text)
