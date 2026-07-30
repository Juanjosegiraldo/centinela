# Centinela

Centinela is an Azure-based fraud and case-management platform built around a
transaction ingestion API, a scoring engine, and a private evidence workflow for
supporting documents. The design keeps secrets out of code, uses managed
identity, and separates the synchronous API path from the asynchronous scoring
and case-handling pipeline.

## What the project does

1. The API receives a transaction, validates it, stores it, and publishes an
   event.
2. The scoring engine consumes that event, evaluates fraud rules, persists the
   scored result, and opens a case when the threshold is reached.
3. Analysts can upload identity documents to a private verification container;
   the system extracts identity data and attaches it to the case for later
   contrast checks.
4. The infrastructure supports load handling and autoscaling so the platform can
   absorb peaks without manual intervention.

## Main components

- [api/](api/) — Ingestion API built with FastAPI.
- [engine/](engine/) — Azure Function scoring engine and case creation logic.
- [infra/](infra/) — Provisioning and shutdown scripts for Azure resources.
- [docs/](docs/) — ADRs, deliverables, and written justifications.
- [tests/](tests/) — Unit tests covering the main behaviours.

## Architecture summary

The API writes the raw transaction, publishes a `transaction-received` event,
and returns immediately. The engine processes the event independently, so the
API never waits for scoring to finish.

For case evidence, the verification documents remain private in Azure Storage.
When a document is uploaded, the system extracts identity information and stores
it alongside the case so downstream contrast logic can use it.

The platform is intentionally credentialless in source control: access relies on
managed identity, Key Vault, and RBAC.

## Supported flows

- Transaction ingestion and asynchronous scoring.
- Case opening when the weighted fraud score crosses the threshold.
- Private document upload with metadata extraction.
- Temporary analyst access to evidence through SAS-based links.
- Load-aware scaling for the API and the scoring engine.

## How to run the platform

### Week 1 foundation

1. Open Azure Cloud Shell (Bash) on an empty subscription.
2. Clone the repository and review the parameters at the top of
   [infra/provision.sh](infra/provision.sh).
3. Run `bash infra/provision.sh`.
4. Deploy the API with the generated Web App name.
5. Test the health endpoint with `curl`.
6. Shut down at the end of the day with `bash infra/shutdown.sh`.

### Week 2 extensions

1. Run [infra/provision-week2.sh](infra/provision-week2.sh) after Week 1.
2. This adds the transaction store, Service Bus, SQL case store, scoring engine,
   and autoscaling rules.
3. The script also wires Document Intelligence configuration for identity
   extraction.

## Operational notes

- No credentials exist in the code, the configuration, the repository, or its
  history.
- The API authenticates with managed identity.
- The scoring threshold is configured in Key Vault so it can be adjusted without
  redeploying the engine.
- The verification documents container is private; access is granted through
  time-limited links.

## Demonstrations and user stories

### Autoscaling

- Owner: Miguel
- Estimate: 3h
- Depends on: W3-02
- API metric: `HttpQueueLength` on the Web App.
- Engine metric: `ActiveMessages` on the Service Bus subscription.
- Policy: minimum 1 instance, maximum 3 instances, with 1-instance scale
  actions and a 5-minute cooldown.
- Demo: generate live traffic, observe instance growth during the peak, and
  confirm the count returns to baseline when the load drops.

### Identity document extraction

- Owner: Miguel
- Estimate: 2h
- Blocks: W3-07
- Trigger: uploading a document to the verification container.
- Service: Document Intelligence F0, with a local fallback for offline/demo
  environments.
- Extracted fields: name, identification number, date of birth, and issue date.
- Result: the extracted data is attached to the case metadata for contrast.
- Free tier note: the F0 tier is appropriate for low-volume demos and should be
  monitored if the upload rate increases significantly.

## Repository structure

- [api/app/main.py](api/app/main.py) — API routes.
- [api/app/storage.py](api/app/storage.py) — storage and document helpers.
- [api/app/events.py](api/app/events.py) — event publishing.
- [engine/function_app.py](engine/function_app.py) — scoring rules and case flow.
- [infra/provision-week2.sh](infra/provision-week2.sh) — week 2 Azure setup.
- [docs/adr.md](docs/adr.md) — architecture decisions and justifications.

## Testing

Run the focused test suite for the new document-extraction flow with:

```bash
python3 -m py_compile api/app/storage.py api/app/main.py tests/test_identity_document_extraction.py
python3 -m unittest tests.test_identity_document_extraction
```

If you want broader coverage, run the full test suite from the repository root.
