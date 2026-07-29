# Deliverable W2-10 — End-to-End Pipeline and Test Report

Owner: Argenis
Maps to: W2-10

## Goal
Document one full transaction path from ingestion to scoring and case handoff, without manual intervention.

## Pipeline summary
1. The API receives a valid transaction.
2. The API validates the contract, persists the raw transaction, publishes the event, and returns 202.
3. The scoring engine consumes the transaction event.
4. The engine evaluates the rules, persists the score, and enqueues the case to `flagged-cases` when the threshold is exceeded.

## Acceptance criteria mapping
- A single transaction produces a score: covered by the scoring tests.
- Above the threshold, a case is produced: the engine marks the transaction as `case_enqueued` and enqueues the case message when the threshold is exceeded.
- No manual step anywhere in the chain: the pipeline is driven by the API and messaging flow.
- The report records every acceptance test with result and evidence: this document is the report placeholder.
- Consumed credit under 40 USD: tracked separately in the cost evidence.

## Evidence
- Unit tests for ingest publishing, queue processing, and scoring.
- API latency measurement for the 202 response.
- Message visible in the topic.
- Cost analysis screenshot.

## Test report status
- Ingestion returns 202 after persistence: pass.
- Event publication occurs before acknowledgment: pass.
- Scoring updates the transaction with score details: pass.
- Threshold crossing sets the case handoff flag and writes the case queue message: pass.

## Notes
- This report follows W2-09 by proving the pipeline is decoupled and durable.
- If the SQL case writer lands later, this report can be extended with the final SQL insertion evidence without changing the ingestion or scoring contracts.