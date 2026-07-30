# Deliverable W3-02 — Container registry and runtime platform

Owner: Juan José · Maps to: Week 3 §2.2, VOR-43.

## What runs where (final state)

| Component | Image | Runs on |
|---|---|---|
| Ingestion API | `acrctndevjj15.azurecr.io/centinela-api:v1` | `app-ctn-ingest-dev-jj15` (Web App for Containers, existing B1 plan) |
| Scoring engine | `acrctndevjj15.azurecr.io/centinela-engine:v1` | `func-ctn-scoring-dev-jj15` (Functions custom container, same B1 plan) |

Both verified live: API `/health` 200 + `POST` 202 with CORS + read endpoint returning real
scores; engine trigger registered, geo-impossible pair → `score=100`, **`sql=True, queued=True`**
— the containerized engine wrote the first SQL case row of the project (the ODBC driver ships
in the image), closing the item deferred since Week 2.

## Registry

- **Azure Container Registry `acrctndevjj15`, Basic tier** (cheapest: 10 GB storage,
  2 webhooks, no geo-replication — limits fit this project).
- Admin user **disabled**. Both web apps pull with **managed identity** (`AcrPull` role,
  `acrUseManagedIdentityCreds=true`). No registry passwords anywhere.
- **Finding (credit ≠ permission, again):** `Microsoft.ContainerRegistry` provider started
  unregistered on this subscription, and **ACR Tasks (`az acr build`) is not permitted**
  (`TasksOperationsNotAllowed`) — cloud builds are unavailable; images are built locally
  (and by CI later) and pushed. Recorded for the ADR.

## Platform choice

**Web App for Containers on the existing B1 plan** — the fallback named in the Jira risk
note, promoted to primary: this subscription's quota history (consumption compute = zero
quota) makes consumption-based container platforms a dead end, and the B1 plan is already
paid for. Managed identity, VNet integration and app settings carry over unchanged.

## Operational gotchas (hard-won, keep for the defense)

1. **App Service mounts the `/home` file share INTO custom containers by default**, hiding
   the image's `/home/site/wwwroot` — the engine initially kept running the OLD deployment
   from the share. Fix: `WEBSITES_ENABLE_APP_SERVICE_STORAGE=false` (both apps).
2. **The API container needs `WEBSITES_PORT=8000`** (platform default probes 80).
3. **ODBC connection-string dialect:** the Key Vault secret was ADO.NET style
   (`User ID=`, `Encrypt=true`); msodbcsql18 rejects it
   (`Invalid value specified for connection string attribute 'Encrypt'`). Rewritten in the
   vault to ODBC dialect (`UID=`, `PWD=`, `Encrypt=yes`, `TrustServerCertificate=no`) —
   a config-only fix, no redeploy (Deliverable 6 in practice).
4. **`publicNetworkAccess=Disabled` on Azure SQL dead-ends the subnet vnet-rule** (that
   mode admits only private endpoints, which are out of project scope). Correct posture per
   the project's own design: public network **enabled** with a **subnet-only firewall**
   (zero IP rules; the snet-app vnet-rule is the single path). Two stale temporary IP rules
   left open by earlier sessions were deleted while verifying.
5. The Service Bus listener takes ~1–2 min after a container (re)start; queued messages
   then drain in a burst — timing-sensitive demos must run against a warm engine.
6. Engine app settings added for containers: `WEBSITES_ENABLE_APP_SERVICE_STORAGE=false`;
   the Function was also VNet-integrated into `snet-app` so the container reaches
   subnet-only SQL.

## Rollback

Both switches are reversible without data impact: reset `linuxFxVersion` to the built-in
runtime and redeploy the previous artifact (zip for the API, bundled-wheels zip for the
engine) — both procedures already exercised earlier in the project.
