# Deliverable 9 — Platform-managed identity for Centinela

Owner: B
Maps to: Deliverable 9

## Goal
Ensure the API authenticates to Azure Storage using a platform-managed identity so that the team never handles credentials (no keys, no secrets, no connection strings in code or repo).

## What is implemented
1. System-assigned managed identity enabled on the Web App by the provisioning script (`infra/provision.sh`).
   - The script runs `az webapp identity assign -g "$RG" -n "$WEBAPP"` and captures the principal id (`APP_MI`).
2. Data-plane roles are granted to that identity scoped to the storage account:
   - `Storage Blob Data Contributor` (write blobs) on the storage account
   - `Storage Queue Data Contributor` (write queue messages) on the storage account
   These assignments are created in `infra/provision.sh` via `az role assignment create` using the storage account scope.
3. No keys, secrets or connection strings are stored in application code, app settings, repository files or git history for storage access. The app uses `DefaultAzureCredential()` to obtain a token at runtime (see `api/app/storage.py`).

## Files to inspect (evidence)
- `infra/provision.sh`:
  - `az webapp identity assign -g "$RG" -n "$WEBAPP"` (enables system-assigned identity)
  - role assignment calls for `Storage Blob Data Contributor` and `Storage Queue Data Contributor` scoped to the storage account id
  - app settings set with `STORAGE_ACCOUNT_URL` and `QUEUE_ACCOUNT_URL` (non-secret endpoints)
- `api/app/storage.py`:
  - `_credential()` returns `DefaultAzureCredential()` which in App Service resolves to the platform managed identity
  - `BlobServiceClient` and `QueueClient` are constructed using the credential (no connection strings or keys used)

## How it satisfies the acceptance criteria
- System-assigned managed identity enabled by the provisioning script: implemented (`az webapp identity assign`).
- Data-plane roles granted to the identity and scoped to the storage account: implemented (`Storage Blob Data Contributor` and `Storage Queue Data Contributor` assigned to `APP_MI` with `$STG_ID` scope).
- No keys, secrets, or connection strings in code or repo: verified — the repo uses URLs in app settings (non-secret) and `DefaultAzureCredential` in code; no storage keys or secrets are present for storage access.

## How to validate locally or in the cloud
1. After provisioning, confirm the managed identity exists:
```bash
az webapp identity show -g <RG> -n <WEBAPP> --query principalId -o tsv
```
2. Confirm role assignments for the storage account:
```bash
STG_ID=$(az storage account show -g <RG> -n <STG> --query id -o tsv)
az role assignment list --scope "$STG_ID" --assignee <principalId>
```
3. At runtime, verify the app can access storage without connection strings by using the `DefaultAzureCredential` path or by testing blob upload from the running app.

## Notes and risks
- Key Vault or other secrets may exist for other Week-2 resources (see `infra/provision-week2.sh`), but those are explicitly stored in Key Vault (controlled, audited) and not in application code or repo.
- If you later need to allow fine-grained data-plane operations (e.g., read-only for Analyst), assign `Storage Blob Data Reader` or scoped roles as needed rather than using storage account keys.

## 30-second explanation for reviewers
The Web App runs with a system-assigned managed identity created by `infra/provision.sh`. The identity receives only the data-plane roles it needs to write transactions and queue messages. The app uses `DefaultAzureCredential` to get tokens from Entra ID at runtime — there are no storage keys or connection strings in the repo or code.
