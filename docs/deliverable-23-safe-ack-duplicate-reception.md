# Deliverable 23 — Safe Acknowledgment and Duplicate Reception Strategy

Owner: C + D
Maps to: Deliverable 23

## Goal
Define the exact point in receive–validate–persist–respond where it is safe to acknowledge acceptance, and document the system behavior when the same transaction is received more than once, so clients can retry without creating inconsistent outcomes.

## Strategy
- The only safe acknowledgment point is **after persistence succeeds**.
- The API must not acknowledge before the raw transaction is durably stored, because an earlier 202 would tell the client the transaction was accepted even if the write never completed.
- The current implementation already follows this rule: validation happens first, persistence happens next, and the 202 response is returned only after `persist_transaction(...)` completes in [api/app/main.py](api/app/main.py).

## Duplicate reception behavior
- Duplicate reception is defined as the same `transaction_id` arriving again.
- The storage key is derived from `transaction_id`, so the transaction is written to the same blob name on every retry in [api/app/storage.py](api/app/storage.py).
- The blob write uses overwrite semantics, so the same payload replaces the previous copy with identical content. The net effect is zero: the stored record remains the same logical transaction.
- Because the write is idempotent, the API can return the same 202 acceptance response on each retry once persistence succeeds.

## Acceptance criteria mapping
- Safe acknowledgment point identified: after persistence, not before.
- Duplicate behavior documented: same `transaction_id` -> same blob name -> overwrite with identical content -> same 202 response.
- Written strategy mandatory: this document is the deliverable artifact.
- Implementation optional this week: no functional change is required here because the code already implements the strategy.

## Operational meaning
- If a client times out after sending a transaction, it can retry safely.
- If the original attempt already persisted, the retry overwrites the same blob with the same content and produces the same logical outcome.
- If the original attempt did not persist, the retry performs the first successful write and then receives 202.

## Verification steps
1. Submit the same transaction twice with the same `transaction_id`.
2. Confirm the stored blob name is identical on both attempts.
3. Confirm the final persisted payload is unchanged.
4. Confirm both requests receive 202 after persistence succeeds.

## Notes
- This strategy complements the queue-burst and poison-message policy in [docs/deliverable-21-22-queue-burst-handling.md](docs/deliverable-21-22-queue-burst-handling.md).
- The implementation is already aligned with the strategy in [api/app/main.py](api/app/main.py) and [api/app/storage.py](api/app/storage.py).