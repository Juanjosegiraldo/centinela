# Architecture Decision Record (ADR)

## ADR 1: Subscription and Region
- **Context:** We need low-latency, supported service availability and a region with sufficient quota for App Service, Storage, SQL, Cosmos, and Service Bus.
- **Decision:** Use `centralus` and a standard subscription type.
- **Consequences:** Good service coverage for Azure, close to typical North American users, and available quota for the Week 1/2 workload.

## ADR 2: App Service plan tier
- **Context:** The API requires VNet integration and managed identity support.
- **Decision:** Use App Service Plan `B1`.
- **Consequences:** Minimal compute cost while supporting VNet integration; it does not scale to zero, but the shutdown script deletes the plan to stop spend.

## ADR 3: Storage redundancy
- **Context:** We need a low-cost durable store for raw transactions and documents.
- **Decision:** Use `Standard_LRS`.
- **Consequences:** Cost-effective durability within a single Azure region; acceptable for Week 1/2 lab workloads.

## ADR 4: Service endpoint vs private endpoint
- **Context:** Storage account must be isolated, but private endpoints add Azure networking complexity and cost.
- **Decision:** Use Azure Storage service endpoints for `snet-app`, with storage firewall default deny.
- **Consequences:** Free isolation mechanism that satisfies Week 2 requirements; note that private endpoints provide stronger isolation and are the paid upgrade path.

## ADR 5: Messaging choice
- **Context:** We need reliable decoupling between API ingestion and downstream processing.
- **Decision:** Use Azure Service Bus Standard: topics for event distribution and queues for guaranteed processing.
- **Consequences:** Supports both pub/sub and durable queue semantics; Service Bus Standard is required for topics and advanced delivery features.

## ADR 6: Contract decisions
- **Context:** Transaction payloads must be deterministic, safe for money, and fit anti-fraud rules.
- **Decision:** Use UUID `transaction_id`, integer minor units, UTC `occurred_at`, latitude/longitude, and forbid extra fields.
- **Consequences:** Enables idempotency, prevents floating-point money errors, supports geo/rule evaluation, and rejects invalid or injection-like payloads.

## ADR 7: Unknown-fields policy
- **Context:** Accepting unknown fields may hide client bugs or malicious payloads.
- **Decision:** Reject unknown fields (`extra='forbid'`).
- **Consequences:** Strict validation surface; clients must send only the declared contract.

## ADR 8: Shutdown responsibility
- **Context:** Week 1 should not incur unnecessary spend overnight.
- **Decision:** Use `infra/shutdown.sh` to stop/delete compute resources daily; keep storage and VNet intact.
- **Consequences:** Cost is minimized while preserving the environment for fast rebuild.
