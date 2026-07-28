import json
import math
import os
from datetime import datetime, timezone

from api.app import storage


DEFAULT_THRESHOLD = 3


def _load_transaction_payload(transaction_id: str) -> dict:
    return storage.load_transaction(transaction_id)


def _threshold() -> int:
    return int(os.environ.get("SCORING_THRESHOLD", str(DEFAULT_THRESHOLD)))


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def _score_rules(payload: dict) -> list[dict]:
    rules: list[dict] = []
    account_id = payload.get("account_id")
    amount_minor = int(payload.get("amount_minor", 0))
    occurred_at = payload.get("occurred_at")
    location = payload.get("location") or {}
    merchant_id = str(payload.get("merchant_id", "")).lower()
    merchant_category = str(payload.get("merchant_category", "")).lower()

    history = storage.load_account_history(account_id) if account_id else []
    occurred_dt = _parse_datetime(occurred_at)
    now = datetime.now(timezone.utc)

    if occurred_dt is not None:
        recent = [
            item for item in history
            if _parse_datetime(item.get("occurred_at")) is not None
            and _parse_datetime(item.get("occurred_at")) < occurred_dt
            and abs((_parse_datetime(item.get("occurred_at")) - occurred_dt).total_seconds()) <= 600
        ]
        if recent:
            rules.append({
                "id": "velocity",
                "triggered": True,
                "observed": {
                    "occurred_at": occurred_at,
                    "previous_occured_at": recent[-1].get("occurred_at"),
                    "window_seconds": 600,
                },
            })
        else:
            rules.append({
                "id": "velocity",
                "triggered": False,
                "observed": {"occurred_at": occurred_at, "now": now.isoformat()},
            })

    if amount_minor > 100000:
        rules.append({
            "id": "atypical_amount",
            "triggered": True,
            "observed": {"amount_minor": amount_minor},
        })

    if location.get("lat") is not None and location.get("lon") is not None:
        lat = float(location["lat"])
        lon = float(location["lon"])
        previous = next((item for item in reversed(history) if item.get("location") is not None), None)
        if previous is not None:
            prev_lat = float(previous["location"]["lat"])
            prev_lon = float(previous["location"]["lon"])
            distance_km = _haversine_km(lat, lon, prev_lat, prev_lon)
            if distance_km > 2000 or (lat > 10 and lon > 70):
                rules.append({
                    "id": "geo_impossible",
                    "triggered": True,
                    "observed": {"location": {"lat": lat, "lon": lon}, "previous_location": {"lat": prev_lat, "lon": prev_lon}, "distance_km": round(distance_km, 2)},
                })
            else:
                rules.append({
                    "id": "geo_impossible",
                    "triggered": False,
                    "observed": {"location": {"lat": lat, "lon": lon}, "previous_location": {"lat": prev_lat, "lon": prev_lon}, "distance_km": round(distance_km, 2)},
                })
        else:
            rules.append({
                "id": "geo_impossible",
                "triggered": False,
                "observed": {"location": {"lat": lat, "lon": lon}},
            })

    if "risk" in merchant_id or "risk" in merchant_category:
        rules.append({
            "id": "risky_merchant",
            "triggered": True,
            "observed": {"merchant_id": merchant_id, "merchant_category": merchant_category},
        })

    return rules


def process_transaction_event(transaction_id: str) -> dict:
    payload = _load_transaction_payload(transaction_id)
    if not payload:
        raise ValueError(f"transaction {transaction_id} not found")

    rules = _score_rules(payload)
    triggered = [rule for rule in rules if rule.get("triggered")]
    score = len(triggered)
    scored_at = datetime.now(timezone.utc).isoformat()

    threshold = _threshold()
    case_enqueued = score > threshold
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
