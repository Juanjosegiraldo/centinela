import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path

try:  # package context (local runs and unit tests)
    from . import store, cases
except ImportError:  # top-level context (Azure Functions host loads function_app.py)
    import store
    import cases

try:
    import azure.functions as func
except ImportError:  # pragma: no cover - Functions runtime absent in local/dev
    func = None


DEFAULT_THRESHOLD = 50

# Weighted 0–100 fraud score: each rule contributes its weight when triggered.
# A case opens when the summed score reaches the threshold (default 50, sourced
# from Key Vault via the SCORING_THRESHOLD app setting — never hardcoded).
RULE_WEIGHTS = {
    "geo_impossible": 60,
    "velocity": 40,
    "atypical_amount": 30,
    "risky_merchant": 25,
}


def _threshold() -> int:
    return int(os.environ.get("SCORING_THRESHOLD", str(DEFAULT_THRESHOLD)))


def _telemetry_path() -> Path:
    root_env = os.environ.get("CENTINELA_LOCAL_STORAGE")
    root = Path(root_env) if root_env else Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root / "scoring-telemetry.jsonl"


def emit_scoring_telemetry(transaction_id: str, duration_ms: int, outcome: str, score: int) -> None:
    telemetry_path = _telemetry_path()
    payload = {
        "transaction_id": transaction_id,
        "duration_ms": duration_ms,
        "outcome": outcome,
        "score": score,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }
    with telemetry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def load_scoring_telemetry(transaction_id: str) -> dict | None:
    telemetry_path = _telemetry_path()
    if not telemetry_path.exists():
        return None
    with telemetry_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("transaction_id") == transaction_id:
                return payload
    return None


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


def _score_rules(payload: dict, history: list[dict]) -> list[dict]:
    rules: list[dict] = []
    amount_minor = int(payload.get("amount_minor", 0))
    occurred_at = payload.get("occurred_at")
    location = payload.get("location") or {}
    merchant_id = str(payload.get("merchant_id", "")).lower()
    merchant_category = str(payload.get("merchant_category", "")).lower()

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


def score_transaction(payload: dict, history: list[dict]) -> dict:
    """Pure scoring, no I/O. Given a transaction and its account history,
    return the weighted score, the rule breakdown and the case decision."""
    rules = _score_rules(payload, history)
    triggered = [rule for rule in rules if rule.get("triggered")]
    score = sum(RULE_WEIGHTS.get(rule["id"], 0) for rule in triggered)
    threshold = _threshold()
    return {
        "transaction_id": str(payload.get("transaction_id", "")),
        "scored": True,
        "score": score,
        "rules": rules,
        "rules_triggered": triggered,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "case_enqueued": score >= threshold,
    }


def handle_transaction(payload: dict) -> dict:
    """Score a transaction and persist the scored record. Single entry point
    shared by the Service Bus trigger and the by-id helper below."""
    started_at = datetime.now(timezone.utc)
    account_id = payload.get("account_id")
    history = store.load_account_history(account_id) if account_id else []
    result = score_transaction(payload, history)

    scored_record = {**payload, **result}
    store.persist_scored_transaction(result["transaction_id"], scored_record)

    if result["case_enqueued"]:
        cases.open_case(result, payload)

    duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    outcome = "case_opened" if result["case_enqueued"] else "scored_only"
    emit_scoring_telemetry(result["transaction_id"], duration_ms, outcome, result["score"])
    return result


def process_transaction_event(transaction_id: str) -> dict:
    """Score a transaction already stored, addressed by id (tests / manual runs
    and the storage-queue consumer)."""
    payload = store.load_transaction(transaction_id)
    if not payload:
        raise ValueError(f"transaction {transaction_id} not found")
    return handle_transaction(payload)


# ---------------------------------------------------------------------------
# Azure Functions v2 entry point: Service Bus topic trigger.
#
# The API publishes to the `transaction-received` topic; this function consumes
# the `scoring-engine` subscription. Topic and subscription names come from app
# settings (%SBUS_TOPIC% / %SBUS_SUBSCRIPTION%). The connection is identity-based
# (managed identity, no keys): set the app setting
# ServiceBusConnection__fullyQualifiedNamespace = <namespace>.servicebus.windows.net.
# The trigger binding is supplied by the extension bundle in host.json, so no
# azure-servicebus dependency is required for the trigger itself.
# ---------------------------------------------------------------------------
if func is not None:  # pragma: no cover - exercised by the Functions runtime
    app = func.FunctionApp()

    @app.service_bus_topic_trigger(
        arg_name="message",
        topic_name="%SBUS_TOPIC%",
        subscription_name="%SBUS_SUBSCRIPTION%",
        connection="ServiceBusConnection",
    )
    def score_on_transaction_received(message: "func.ServiceBusMessage") -> None:
        event = json.loads(message.get_body().decode("utf-8"))
        # The API publishes an envelope {event_type, record, published_at, topic}.
        # Accept both the enveloped form and a bare transaction payload.
        payload = event.get("record", event) if isinstance(event, dict) else event
        result = handle_transaction(payload)
        logging.info(
            "scored transaction %s: score=%s case=%s",
            result["transaction_id"], result["score"], result["case_enqueued"],
        )
