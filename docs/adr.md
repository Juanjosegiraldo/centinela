# Architecture Decision Record — Centinela

Format: context -> decision -> consequences. One entry per significant decision.

## Week 1

### ADR-01 · Subscription type
Context: Azure for Students was not available (Universidad de Medellín is not
registered in the program; the institution never appears in Microsoft's
eligibility list). Decision: use the standard free trial (200 USD, 30 days,
spending limit on). Consequences: matches the "limited credit, 30-day validity"
subscription the brief describes; the 21-day project fits within the window.

### ADR-02 · Region: centralus
Context: East US reported zero App Service B1 quota for this subscription
despite available credit. Six regions were tested. Decision: deploy to Central
US, the first region with B1 quota and with Document Intelligence F0 available.
Consequences: ~10-20 ms extra latency from Colombia, irrelevant for the project;
the justification is now evidence-based rather than assumed.

### ADR-03 · App Service tier B1
Context: VNet integration requires a tier that supports it; F1/D1 do not.
Decision: B1, the lowest tier that supports VNet integration. Consequences:
~13 USD/month if 24/7; nightly shutdown keeps the week under 5 USD.

### ADR-04 · Storage redundancy LRS
Context: evidence preservation for a 21-day project. Decision: LRS, the cheapest
redundancy. Consequences: three copies in one datacenter; production would use
ZRS/GRS. Documented as a cost decision.

### ADR-05 · Service endpoints over private endpoints
Context: the storage account must be unreachable from the internet. Decision:
service endpoints + storage firewall (free) instead of private endpoints (~7
USD/month). Consequences: traffic from the app subnet routes over the Azure
backbone; storage rejects everything else. Private endpoints would add a private
IP inside the VNet; not justified for this budget.

### ADR-06 · Resource providers must be registered
Context: a fresh subscription starts with resource providers unregistered; even
quota queries failed until registering them. Decision: register providers as a
prerequisite step. Consequences: reinforces the "credit is not capacity"
principle; each new service type needs its provider registered.

### ADR-07 · Role assignment is not idempotent
Context: assigning a role to a just-created managed identity fails because the
identity has not propagated in Entra ID; the original script silenced the error
and left the app unable to write. Decision: retry with backoff and stop on a
genuine failure instead of silencing it. Consequences: the script is now
reproducible from scratch; the managed identity gets its roles without manual
intervention.

## Week 2

### ADR-08 · Transaction store partition key /account_id
Context: the dominant query is "recent transactions of one account", run by the
scoring engine on every transaction. Decision: partition by /account_id.
Consequences: that query reads a single partition (cheap, scalable). Sacrifices
cross-account queries, which the system does not need. Alternatives discarded:
/transaction_id (scatters an account's history across all partitions, forcing
cross-partition reads) and /merchant_id (optimises by merchant, not by account).
The partition key cannot be changed without full data migration, so it was fixed
before the first write.

### ADR-09 · Consistency level Session
Context: the engine reads history it wrote itself; there is no need for globally
strong consistency. Decision: Session consistency (the default). Consequences:
reads are consistent within a session at low latency; strong consistency would
add latency for a guarantee this use case does not require.

### ADR-10 · TTL 90 days on the transaction store
Context: the longest rule window (atypical amount vs history) needs recent
history; nothing looks back further. Decision: TTL of 90 days. Consequences:
records past the longest window auto-delete; storage stays bounded without a
cleanup job.

### ADR-11 · Messaging over direct invocation
Context: the API must respond before scoring finishes (central architectural
requirement). Decision: the API publishes an event to a Service Bus topic and
returns; the engine reacts independently. Consequences: ingestion and analysis
are decoupled; the API response time does not depend on the engine. A direct
call would satisfy the output and break the requirement.

### ADR-12 · Topic vs queue
Context: two messaging needs with different semantics. Decision: a topic for the
transaction event (announce that it happened; any subscriber may react) and a
queue for flagged cases (guarantee processing; nothing lost if the consumer is
down). Consequences: notification and guaranteed processing are handled by the
mechanism suited to each. Service Bus Standard is required because topics need
Standard; Basic offers queues only.

### ADR-13 · Score threshold in Key Vault
Context: the threshold must change without redeploying. Decision: store it as a
Key Vault secret, read at execution time. Consequences: changing the value in
the vault takes effect within minutes without a deployment; the engine is
serverless with short-lived instances. Justification of the value: a starting
threshold of 50 balances false positives against undetected fraud, tunable as
real data appears.

### ADR-14 · Azure SQL serverless with auto-pause
Context: the case store has low volume and is queried by analysts, not in real
time. Decision: serverless with auto-pause at 60 min. Consequences: it bills
only while active; the first query after inactivity incurs a ~30-60 s wake-up
latency, acceptable for this access pattern.

### ADR-15 · Key Vault create is not idempotent
Context: `az keyvault create` fails if the vault already exists, stopping the
re-run of the provisioning script. Decision: tolerate the "already exists" error
and continue. Consequences: the week 2 script can be re-run like the week 1 one.

### ADR-16 · Scoring engine on the B1 plan
Context: the Linux consumption plan (dynamic workers) is unavailable in this
subscription in every region tested. Decision: run the Function on the existing
B1 App Service plan. Consequences: the event trigger is preserved (the
architectural requirement); scale-to-zero is lost, acceptable since the B1 plan
is already provisioned and paid for.
