# Deliverable 8 — Azure role permissions matrix

This matrix separates control plane permissions from data plane permissions and ties every assignment to a concrete system operation.

## Design principle

Every role receives only the Azure permissions needed for the operations that role must perform. If a permission does not support a concrete operation in the system, it is not granted.

## Role matrix

| Role | Plane | Azure built-in role | Scope | Concrete system operation requiring the permission | Why this role is appropriate |
|---|---|---|---|---|---|
| Service (web app managed identity) | Data plane | Storage Blob Data Contributor | Storage account | Persist raw transactions and store verification documents in blob containers | The application writes transaction payloads and case evidence to Azure Storage. |
| Service (web app managed identity) | Data plane | Storage Queue Data Contributor | Storage account | Enqueue incoming transactions for downstream processing | The application must publish the transaction-received event to the ingest queue. |
| Analyst | Control plane | Reader | Resource group | Inspect deployed resources and infrastructure metadata | The analyst needs visibility over the solution state without changing it. |
| Analyst | Data plane | Storage Blob Data Reader | Storage account | Read verification evidence blobs for analysis | The analyst needs to review case evidence already stored by the application. |
| Auditor | Control plane | Reader | Resource group | Review deployed resources and configuration without modifying them | The auditor needs oversight of the environment without operational changes. |
| Auditor | Data plane | Storage Blob Data Reader | Storage account | Read verification evidence blobs for audit review | The auditor needs access to stored evidence to validate the process. |
| Admin | Control plane | Contributor | Resource group | Manage the deployment lifecycle (create/update/delete resources, app settings, networking, and role assignments) | The administrator needs to operate and maintain the infrastructure. |

## Notes on built-in roles

The built-in roles were reviewed before assignment to avoid broader permissions than necessary:

- Reader is read-only and is appropriate for inspection tasks.
- Contributor is a control-plane role and is appropriate only for the Admin role because it can manage infrastructure resources.
- Storage Blob Data Contributor/Reader and Storage Queue Data Contributor are data-plane roles and are used only where the application or a human operator needs to work with stored data or queue messages.
- No assignment grants the Service role control-plane administration rights.
