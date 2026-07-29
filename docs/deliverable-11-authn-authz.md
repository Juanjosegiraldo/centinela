# Deliverable 11 — Authentication and Authorization in Centinela

Owner: B
Maps to: Deliverable 11

## Purpose
Short note describing where authentication and authorization occur in Centinela, with one concrete example of each applied to this codebase.

## Key concepts (brief)
- Authentication (AuthN): verifying the identity of a principal (user or service).
- Authorization (AuthZ): deciding whether an authenticated principal is allowed to perform a specific action.

## Where Authentication happens in Centinela (concrete)
- Location in repo: [api/app/storage.py](api/app/storage.py) and [infra/provision.sh](infra/provision.sh).
- Mechanism used: Azure Managed Identity + Microsoft Entra ID (Azure AD).

Concrete example (AuthN): managed identity obtaining a token
- When the Web App is created, the provisioning script runs `az webapp identity assign` and stores the managed identity principal for the app (see `infra/provision.sh`).
- At runtime the application uses `DefaultAzureCredential()` (see `api/app/storage.py` in `_credential()`), which under App Service resolves to the Web App's managed identity.
- The managed identity requests an OAuth2 access token from Microsoft Entra ID (Azure AD) for the target resource (for example, Azure Storage). Entra ID validates the request and issues a token bound to that identity.
- Outcome: the Web App is authenticated — it holds a valid access token proving its identity to Azure services.

Why this is AuthN: the token issuance step by Entra ID is the act of proving identity (the app receives credentials from the identity provider).

## Where Authorization happens in Centinela (concrete)
- Location in repo: [infra/provision.sh](infra/provision.sh) (role assignments) and runtime access control occurs in Azure when interacting with storage (see `api/app/storage.py`).
- Mechanism used: Azure Role-Based Access Control (RBAC) evaluated by Azure Storage when the token is presented.

Concrete example (AuthZ): RBAC evaluation at the storage account
- The provisioning script assigns `Storage Blob Data Contributor` and `Storage Queue Data Contributor` to the Web App managed identity scoped at the storage account (see `infra/provision.sh`).
- Suppose an `Auditor` user authenticates successfully (for example, using Azure Portal) and holds only `Reader` + `Storage Blob Data Reader` roles.
- If the Auditor issues a write request to the Storage account (for example, attempts to upload a blob), Azure will perform RBAC evaluation: the authenticated principal (Auditor) does not have a data-plane write role (Blob Data Contributor) and therefore the write request is denied with an authorization error.
- Outcome: identity is authenticated, but the action is denied because RBAC does not permit it — this is authorization enforcement.

Why this is AuthZ: RBAC checks whether the authenticated principal is permitted to perform a specific operation on the resource; the decision is the authorization result.

## Notes specific to Centinela
- Authentication is handled by Microsoft Entra ID; code does not handle password or token exchange directly — it relies on `DefaultAzureCredential` and the platform's managed identity.
- Authorization decisions are enforced by Azure services (Storage, Queue) based on RBAC role assignments created by the provisioning script. The application code assumes successful authorization; it does not implement policy checks itself.
- Files of interest:
  - `api/app/storage.py` — uses `DefaultAzureCredential` and creates `BlobServiceClient`/`QueueClient` with those credentials.
  - `infra/provision.sh` — assigns managed identity and creates role assignments (`Storage Blob Data Contributor`, `Storage Queue Data Contributor`, `Reader`, `Storage Blob Data Reader`, `Contributor`).

## 30-second explanation (to use in a review)
- Authentication: the Web App uses a managed identity that obtains a token from Microsoft Entra ID (see `infra/provision.sh` + `api/app/storage.py`).
- Authorization: Azure RBAC enforces permissions at the storage account; an authenticated Auditor without write permission will be denied when trying to upload a blob.

## 1-minute example walkthrough (for demos)
1. Provision: `infra/provision.sh` creates the Web App and assigns a managed identity, then grants it `Storage Blob Data Contributor` against the storage account.
2. Runtime AuthN: the app calls `DefaultAzureCredential()` to obtain a token from Entra ID; token proves the app identity.
3. Runtime AuthZ: app calls blob upload API with the token; Azure Storage verifies RBAC and allows the write because the app identity has `Storage Blob Data Contributor`.
4. Contrast: an Auditor user authenticates successfully but lacks write roles; a write attempt is rejected by RBAC.

---

If you want, I can also: 
- add a short diagram, or
- include HTTP traces and sample `az rest` commands that demonstrate obtaining tokens and a denied write.
