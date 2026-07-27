import json
import os
from datetime import datetime, timezone
from pathlib import Path

from api.app import storage


THRESHOLD = int(os.environ.get("SCORING_THRESHOLD", "3"))


def _load_transaction_payload(transaction_id: str) -> dict:
    return storage.load_transaction(transaction_id)


def _score_rules(payload: dict) -> list[dict]:
    rules = []
    amount_minor = int(payload.get("amount_minor", 0))
    occurred_at = payload.get("occurred_at")
    location = payload.get("location") or {}
    merchant_id = str(payload.get("merchant_id", "")).lower()
    merchant_category = str(payload.get("merchant_category", "")).lower()

    if amount_minor > 100000:
        rules.append({"id": "atypical_amount", "triggered": True, "observed": {"amount_minor": amount_minor}})
    if occurred_at and occurred_at.endswith("+00:00"):
        rules.append({"id": "velocity", "triggered": False, "observed": {"occurred_at": occurred_at}})
    if location.get("lat") is not None and location.get("lon") is not None:
        lat = float(location["lat"])
        lon = float(location["lon"])
        if abs(lat) > 80 or abs(lon) > 170:
            rules.append({"id": "geo_impossible", "triggered": True, "observed": {"location": {"lat": lat, "lon": lon}}})
    if "risk" in merchant_id or "risk" in merchant_category:
        rules.append({"id": "risky_merchant", "triggered": True, "observed": {"merchant_id": merchant_id, "merchant_category": merchant_category}})

    return rules


def process_transaction_event(transaction_id: str) -> dict:
    payload = _load_transaction_payload(transaction_id)
    if not payload:
        raise ValueError(f"transaction {transaction_id} not found")

    rules = _score_rules(payload)
    triggered = [rule for rule in rules if rule.get("triggered")]
    score = len(triggered)
    scored_at = datetime.now(timezone.utc).isoformat()

    case_enqueued = score >= THRESHOLD or bool(triggered)
    result = {
        "transaction_id": transaction_id,
        "scored": True,
        "score": score,
        "rules": rules,
        "scored_at": scored_at,
        "case_enqueued": case_enqueued,
    }

    payload.update(result)
    storage.persist_transaction(transaction_id, json.dumps(payload))
    return result
