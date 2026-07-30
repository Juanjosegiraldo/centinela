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

## Scaling and load demonstration (HU)
- Owner: Miguel
- Estimate: 3h
- Depends on: W3-02
- API metric: HttpQueueLength on the Web App. This is the best leading indicator
  for the ingestion API under burst traffic because it captures the backlog of
  incoming requests before the service becomes visibly unhealthy.
- Engine metric: ActiveMessages on the Service Bus subscription used by the
  scoring engine. This matches the backlog of work waiting to be processed and
  directly reflects whether the engine is falling behind during a peak.
- Autoscaling policy: both services are configured for a minimum of 1 instance,
  a maximum of 3 instances, and a 1-instance scale-out/scale-in action with a
  5-minute cool-down. The policy is intended to absorb burst traffic without
  forcing the team to manually intervene.
- Demo procedure: generate live traffic against the API while watching the Web
  App instance count and the Service Bus subscription backlog. The API should
  scale out first during the peak, then the engine should start processing the
  backlog and scale out if the subscription depth remains elevated. Once the
  traffic stops, the instance count should return to baseline.
- Saturation point and mitigation: the component that saturates first is the
  one whose selected metric breaches its threshold earliest. In the current
  design that is expected to be the API during the ingest burst, so the
  mitigation is to keep the auto-scale policy aggressive enough to add capacity
  quickly and to avoid a long queue on the ingestion path.

## Identity document extraction (HU)
- Owner: Miguel
- Estimate: 2h
- Blocks: W3-07
- Trigger: uploading a document to the verification container now runs an
  extraction step automatically after the blob is stored.
- Service: Document Intelligence F0 is the intended service for production
  deployments; the implementation is wired for that path and uses a local text
  heuristic in environments where the Azure SDK is not configured.
- Extracted fields: name, identification number, date of birth and issue date
  are captured and attached to the case metadata record so later contrast
  checks can use them.
- Free tier limits: F0 is suitable for low-volume demos and lab traffic, but
  the expected volume should stay within the free-tier quota for the subscription
  and the implementation should be monitored if the upload rate grows beyond a
  few hundred documents per day.
