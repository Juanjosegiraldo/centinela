# Deliverable W2-04 — Publish Transaction Event from the API

Owner: Miguel
Maps to: W2-04

## Goal
Make the ingestion API publish an event after the transaction is durably stored and return immediately, so the client never waits for fraud analysis.

## Strategy
- The safe point to emit the event is **after persistence succeeds** and **before acknowledgment**.
- The API must not call the scoring engine directly.
- The API must not wait for fraud analysis to finish before returning 202.
- The published event is the signal that downstream components may react to the new transaction.

## Implementation notes
- The ingestion flow in [api/app/main.py](api/app/main.py) already persists the raw transaction first, then calls `events.publish_transaction_received(...)`, and only then returns 202.
- The event publisher in [api/app/events.py](api/app/events.py) now targets the Service Bus topic configured by `SERVICEBUS_FQDN` and `SBUS_TOPIC`, and sends the full transaction record as JSON.
- In local development, the same publisher writes to a local topic log so the flow remains testable without Azure.
- The engine is still decoupled: the API only publishes the event; it does not score the transaction itself.

## Acceptance criteria mapping
- Publishes to the topic after persisting, before acknowledging: yes.
- Does not call the engine and does not wait for a result: yes.
- Valid transaction still returns 202: yes.

## Evidence
- A valid request returns 202 and the response time is the API latency.
- The event appears in the topic for downstream consumption.

## Verification steps
1. Send a valid transaction to `/transactions`.
2. Confirm the API returns 202 immediately after persistence.
3. Confirm the event is visible in the Service Bus topic `transaction-received`.
4. Confirm the scoring engine is not called by the API path.

## Notes
- This story depends on W2-01 because the topic and permissions are provisioned there.
- This story blocks W2-07 because the engine can only react once the API emits the event.