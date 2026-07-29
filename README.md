# Centinela — Week 1

Infrastructure repository and transaction ingestion API.

## Structure
- `infra/provision.sh` — Provisioning (parameterized, idempotent).
- `infra/shutdown.sh` — End-of-day shutdown (`--full` deletes everything).
- `api/` — Ingestion API (FastAPI, managed identity, credentialless).
- `docs/` — Written deliverables (quota report, region justification, ADR).

## Deployment from scratch (Deployment README — Deliverable 26)
1. Open Azure Cloud Shell (Bash) on an empty subscription.
2. Clone this repository.
3. Edit the parameters at the top of `infra/provision.sh`:
   - `UNIQUE_SUFFIX` must be globally unique.
   - `PROJECT`, `ENVIRONMENT`, `LOCATION` can be left as-is for this lab.
4. Run the provisioning script:
   ```bash
   bash infra/provision.sh
   ```
5. Deploy the API from the root of the repo:
   ```bash
   cd api
   zip -r ../api.zip .
   az webapp deploy -g rg-ctn-dev -n app-ctn-ingest-dev-<SUFFIX> --src-path ../api.zip --type zip
   ```
6. Verify the API:
   ```bash
   curl https://app-ctn-ingest-dev-<SUFFIX>.azurewebsites.net/health
   ```
7. When done for the day, stop compute and retain storage/VNet:
   ```bash
   bash infra/shutdown.sh
   ```

### What is included
- `infra/provision.sh` provisions the resource group, VNet/subnets, NSGs, storage account, App Service plan, web app, identity, role assignments, and storage isolation rules.
- `infra/provision-week2.sh` provisions Week 2 resources: Cosmos DB, Azure SQL, Service Bus, Key Vault, Function App, and secure network access.
- `infra/shutdown.sh` stops compute spend by deleting the App Service and plan, or deletes the entire resource group with `--full`.

### Verified assumptions
- No credentials are stored in code, configuration, or git history.
- The API uses the managed identity assigned to the App Service.
- The network is isolated with service endpoints and firewall restrictions.

### Additional documentation
- `docs/network_topology.md` — VNet/subnet topology and component placement.
- `docs/nsg_rules.md` — NSG rules, sources, destinations, ports, and operational justification.
- `docs/adr.md` — Architecture Decision Record with Week 1 decisions and consequences.
