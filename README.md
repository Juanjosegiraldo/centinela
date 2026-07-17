# Centinela — Week 1

Infrastructure repository and transaction ingestion API.

## Structure
- `infra/provision.sh` — Provisioning (parameterized, idempotent).
- `infra/shutdown.sh` — End-of-day shutdown (`--full` deletes everything).
- `api/` — Ingestion API (FastAPI, managed identity, credentialless).
- `docs/` — Written deliverables (quota report, region justification, ADR).

## Deployment from scratch (Deployment README — Deliverable 26)
1. Open Azure Cloud Shell (Bash) on an empty subscription.
2. Clone this repository and edit the parameters at the top of
   `infra/provision.sh` (`UNIQUE_SUFFIX` is required and must be globally unique).
3. `bash infra/provision.sh`
4. Deploy the API:
   `cd api && zip -r ../api.zip . && az webapp deploy -g rg-ctn-dev -n app-ctn-ingest-dev-<SUFFIX> --src-path ../api.zip --type zip`
5. Test: `curl https://app-ctn-ingest-dev-<SUFFIX>.azurewebsites.net/health`
6. At the end of each workday: `bash infra/shutdown.sh`

No credentials exist in the code, the configuration, the repository or its
history: the API authenticates with the platform's managed identity.
