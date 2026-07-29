import csv, os, json
from fetch_persisted_records import read_blob
from datetime import datetime

IN = os.environ.get("IN_CSV","evidence_pending.csv")
OUT = os.environ.get("OUT_CSV","final_evidence.csv")

def parse_iso(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

with open(IN, newline='') as fin, open(OUT, 'w', newline='') as fout:
    r = csv.DictReader(fin)
    w = csv.writer(fout)
    w.writerow(["transaction_id","client_sent_at","client_response_at","received_at","processed_at"]) 
    for row in r:
        tid = row['transaction_id']
        received_at = ''
        processed_at = ''
        try:
            raw = read_blob('raw-transactions', f"{tid}.json")
            received_at = raw.get('received_at','')
        except Exception:
            received_at = ''
        try:
            proc = read_blob(os.environ.get('PROCESSED_CONTAINER','processed-transactions'), f"{tid}.json")
            processed_at = proc.get('processed_at','')
        except Exception:
            processed_at = ''
        w.writerow([tid, row['client_sent_at'], row['client_response_at'], received_at, processed_at])
print('Wrote', OUT)
