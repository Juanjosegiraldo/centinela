# Closure Validation and Proof-of-Work

This document captures the Week 1 closure validation steps and the evidence required for the VOR issue set.

## Goal
Deliver the proof that the system can be rebuilt from scratch, accepts valid transactions, rejects invalid payloads, persists raw transaction data, stores trace evidence, and preserves the decoupled queue flow.

## Sequence
1. Start with an empty subscription.
2. Clone the repository and review the parameters in `infra/provision.sh`.
3. Run `bash infra/provision.sh` from the repository root.
4. Deploy the API from `api/`:
   ```bash
   cd api
   zip -r ../api.zip .
   az webapp deploy -g rg-ctn-dev -n app-ctn-ingest-dev-<SUFFIX> --src-path ../api.zip --type zip
   ```
5. Verify the health endpoint:
   ```bash
   curl https://app-ctn-ingest-dev-<SUFFIX>.azurewebsites.net/health
   ```
6. Send a valid sample transaction:
   ```bash
   curl -X POST https://app-ctn-ingest-dev-<SUFFIX>.azurewebsites.net/transactions \
     -H 'Content-Type: application/json' \
     -d '{"transaction_id":"<uuid>","account_id":"acct-01","amount_minor":100,"currency":"USD","occurred_at":"2026-07-29T00:00:00Z","location":{"lat":0.0,"lon":0.0},"merchant_id":"m-1","merchant_category":"general"}'
   ```
7. Verify raw persistence:
   - Check the blob `raw-transactions/<transaction_id>.json` exists.
   - Check the trace blob `verification-docs/trace/<transaction_id>.json` exists.
8. Simulate consumer downtime and queue durability:
   - Start the consumer from `tools/consumer.py` in a separate terminal.
   - Stop the consumer and send 10 valid transactions.
   - Restart the consumer and verify all messages are processed to `processed-transactions/`.
9. Validate invalid payload handling:
   - Send a transaction with an unsupported currency or extra field.
   - Confirm the API returns `400` and does not store the blob.
10. Verify network isolation proof:
   - From an external network or a host outside `snet-app`, confirm storage access is denied.
   - The storage account is locked down by service endpoint allow and default deny.
11. Generate final evidence:
   - Collect the raw transaction blobs, trace blobs, processed blobs, and the `closure_validation` checklist.
   - Record the total consumed credit and confirm the cost constraint under $60.
12. When finished, run:
   ```bash
   bash infra/shutdown.sh
   ```

## Evidence artifacts
- `verification-docs/trace/<transaction_id>.json`
- `raw-transactions/<transaction_id>.json`
- `processed-transactions/<transaction_id>.json` (after consumer replay)
- `docs/closure_validation.md`
- `docs/final_cost_report.md`

## Acceptance criteria covered
- VOR-29: full deployment README reproducibility
- VOR-30: closure validation sequence executed and logged
- VOR-53: rebuild from README and final decision record
- VOR-40: queue durability proof with consumer downtime
- VOR-50: per-transaction trace evidence persisted
- VOR-51: alert conditions documented and operationally verified
- VOR-16/17/18: network topology, deny-by-default rules, storage isolation proofs
