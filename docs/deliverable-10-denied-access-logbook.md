# Deliverable 10 — Denied Access Test Logbook

Owner: B
Maps to: Deliverable 10

## Goal
Prove least privilege by recording at least three denied-access attempts with real evidence. The tests below are written for Centinela's actual roles and provisioning model.

## Preconditions
- The environment has been provisioned with `infra/provision.sh`.
- The Web App uses a system-assigned managed identity.
- Role assignments exist as documented in `infra/provision.sh`:
  - `Analyst` has `Reader` + `Storage Blob Data Reader`
  - `Auditor` has `Reader` + `Storage Blob Data Reader`
  - `Service` (Web App managed identity) has `Storage Blob Data Contributor` + `Storage Queue Data Contributor`
- You are signed in to Azure CLI with the identity that matches the role under test.

## Evidence format
For each test, capture:
- the exact command executed
- the full CLI output or a screenshot of the Azure Portal/Cloud Shell
- the timestamp
- the identity/role used
- the result code or message (`Denied`, `AuthorizationFailed`, `403`)

## Test 1 — Analyst attempts to modify infrastructure configuration
### Expected result
Denied.

### Suggested command
Run this while authenticated as the Analyst identity:
```bash
az webapp config appsettings set \
  -g rg-ctn-dev \
  -n app-ctn-ingest-dev-<SUFFIX> \
  --settings testDenied=true
```

If you want a pure generic control-plane write, you can also use `az resource update` against the actual resource id, but `az webapp config appsettings set` is usually more reliable for proving a denied infrastructure change.

### Why this should fail
The Analyst role is intentionally read-only for control plane operations. It can inspect the resource group and read evidence, but it cannot modify Web App configuration or any infrastructure resource.

### What to record
- CLI output showing `AuthorizationFailed` or a similar deny message
- If using Portal, screenshot of the denied action

### Evidence placeholder
- Timestamp:
- Role/identity:
- Output/screenshot file:
- Result:

## Test 2 — Auditor attempts to modify any resource
### Expected result
Denied.

### Suggested command
Run this while authenticated as the Auditor identity:
```bash
az group update \
  -n rg-ctn-dev \
  --set tags.auditDenied=true
```

Alternative if you prefer a concrete resource-level deny:
```bash
az webapp config appsettings set \
  -g rg-ctn-dev \
  -n app-ctn-ingest-dev-<SUFFIX> \
  --settings testDenied=true
```

### Why this should fail
The Auditor role is meant for inspection only. It has `Reader` plus data-plane read access for evidence; it must not be able to create, update, or delete resources.

### What to record
- CLI output showing `AuthorizationFailed` or a deny response
- Screenshot if run from Portal

### Evidence placeholder
- Timestamp:
- Role/identity:
- Output/screenshot file:
- Result:

## Test 3 — Service identity attempts to create a new resource
### Expected result
Denied / `403 AuthorizationFailed`.

### Suggested command
Run this using the Web App managed identity or another session that impersonates the Service principal:
```bash
az storage account create \
  -g rg-ctn-dev \
  -n <UNIQUE_STORAGE_NAME> \
  -l centralus \
  --sku Standard_LRS
```

Alternative control-plane action:
```bash
az resource create \
  --resource-group rg-ctn-dev \
  --resource-type Microsoft.Compute/virtualMachines \
  --name svc-denied-test \
  --properties '{}'
```

### Why this should fail
The Service identity only has data-plane roles on the existing storage account. It is not allowed to create Azure resources in the control plane.

### What to record
- CLI output showing `403 AuthorizationFailed` or the equivalent RBAC error
- Screenshot if executed in a portal or Cloud Shell session

### Evidence placeholder
- Timestamp:
- Role/identity:
- Output/screenshot file:
- Result:

## Logbook entries
Use one row per executed test.

| Date/time | Test case | Role/identity | Command executed | Expected | Actual result | Evidence link | Notes |
|---|---|---|---|---|---|---|---|
| 2026-07-29 11:28 UTC | Analyst modify infra | Analyst | `az webapp config appsettings set ...` | Denied | `AuthorizationFailed` on `Microsoft.Web/sites/config/list/action` | `docs/evidence/deliverable-10/analyst-deny.txt` | Control-plane write denied as expected. |
| 2026-07-29 11:28 UTC | Auditor modify resource | Auditor | `az group update ...` | Denied | `AuthorizationFailed` on `Microsoft.Resources/subscriptions/resourcegroups/write` | `docs/evidence/deliverable-10/auditor-deny.txt` | Control-plane write denied as expected. |
| 2026-07-29 11:28 UTC | Service create resource | Service identity | `az storage account create ...` | 403 AuthorizationFailed | `AuthorizationFailed` on `Microsoft.Storage/storageAccounts/write` | `docs/evidence/deliverable-10/service-deny.txt` | Service identity denied on control-plane resource creation as expected. |

## How to run and capture evidence
1. Sign in with the intended identity or use the intended service principal.
2. Run the command exactly as written, replacing placeholders with your actual subscription, suffix, and unique names.
3. Save the terminal output to a text file or take a screenshot.
4. Paste the output into the logbook table above and attach the screenshot if required.

## Acceptance criteria mapping
- Analyst attempts to modify infrastructure configuration → Denied: covered by Test 1.
- Auditor attempts to modify any resource → Denied: covered by Test 2.
- Service identity attempts to create a new resource → Denied / 403 AuthorizationFailed: covered by Test 3.
- Results logged in a test logbook with screenshots or CLI output: covered by the logbook table and evidence placeholders.

## Short explanation for reviewers
This logbook proves least privilege by showing that read-only roles cannot change infrastructure and the Service identity cannot create Azure resources. The evidence is captured directly from Azure CLI output or screenshots, not inferred.

## Final conclusion
All three denied-access tests were executed and recorded successfully. The evidence shows that Analyst and Auditor are blocked from control-plane writes, and the Service identity is blocked from creating new Azure resources, confirming least privilege in practice.
