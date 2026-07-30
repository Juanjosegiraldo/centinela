import requests, uuid, csv, time, os
from datetime import datetime, timezone

API=os.environ.get("API_URL","http://localhost:8000")
OUT=os.environ.get("OUT_CSV","evidence_pending.csv")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def make_tx():
    return {
        "transaction_id": str(uuid.uuid4()),
        "account_id": "acct-01",
        "amount_minor": 100,
        "currency": "USD",
        "occurred_at": now_iso(),
        "location": {"lat": 0.0, "lon": 0.0},
        "merchant_id": "m-1",
        "merchant_category": "general"
    }

N = int(os.environ.get("N", "50"))
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["transaction_id","client_sent_at","client_response_at","status","http_code"]) 
    for i in range(N):
        tx = make_tx()
        sent = now_iso()
        try:
            r = requests.post(API+"/transactions", json=tx, timeout=10)
            resp_at = now_iso()
            tid = tx["transaction_id"]
            w.writerow([tid, sent, resp_at, r.text[:200].replace('\n',' '), r.status_code])
        except Exception as e:
            resp_at = now_iso()
            w.writerow([tx["transaction_id"], sent, resp_at, f"error:{e}", 0])
        time.sleep(float(os.environ.get("DELAY", "0.05")))
print("Wrote", OUT)
