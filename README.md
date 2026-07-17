# Centinela — Week 1

Infrastructure repository and ingestion API.

## Structure
- `GUIA_SEMANA1.md` — Complete step-by-step guide with evidence and costs.
- `infra/provision.sh` — Provisioning (configurable, idempotent).
- `infra/shutdown.sh` — end-of-day shutdown (`--full` deletes everything).
- `api/` — Ingestion API (FastAPI, managed identity, credentialless).

## Deployment from scratch (Deployment README — Deliverable 26)
1. Open Azure Cloud Shell (Bash) in an empty subscription.
2. Clone this repository and edit the parameters at the beginning of `infra/provision.sh`
   (`UNIQUE_SUFFIX` required: must be globally unique).
3. `bash infra/provision.sh`
4. `cd api && zip -r ../api.zip . && az webapp deploy -g rg-ctn-dev -n app-ctn-ingesta-dev-<SUFFIX> --src-path ../api.zip --type zip`
5. Test: `curl https://app-ctn-ingesta-dev-<SUFFIX>.azurewebsites.net/health`
6. At the end of the day: `bash infra/shutdown.sh`

There are no credentials in the code or in the configuration: the API
authenticates using the platform’s managed identity.

