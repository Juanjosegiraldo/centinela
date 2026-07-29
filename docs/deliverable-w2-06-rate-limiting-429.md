# Deliverable W2-06 — Per-Origin Rate Limiting Returning 429

Owner: Miguel
Maps to: W2-06

## Goal
Limit abusive burst traffic so synthetic requests cannot drain credit by pushing unnecessary work into the fraud pipeline.

## Strategy
- Apply the limit to the ingestion path only.
- Count requests per origin using the request IP or `x-forwarded-for` when present.
- Reject requests once the origin exceeds the configured budget within the configured time window.

## Chosen budget
- Limit: 60 requests per minute.
- Window: 60 seconds.
- Justification: high enough for normal ingestion bursts, low enough to stop unbounded synthetic load from chewing through fraud-processing capacity.

## Acceptance criteria mapping
- Requests beyond the limit return 429: implemented.
- Limit value and window documented and justified: documented here.
- Limitations documented: in-memory counting is per app instance and resets on restart.

## Limitations
- The counter is in memory, so it is not shared across multiple scaled-out instances.
- Restarting the app clears counters.
- The protection is intentionally lightweight and fits the current single-instance budget.

## Evidence
- Burst test output showing a 429 response after the per-origin limit is exceeded.

## Verification steps
1. Send repeated POST requests to `/transactions` from the same origin.
2. Confirm the first requests return 202.
3. Confirm the request after the limit returns 429.