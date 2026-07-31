# Deliverable 19 — Private Verification Documents and Delegated Access

Owner: C + D
Maps to: Deliverable 19

## Goal
Provide a private container for identity-verification documents with temporary delegated access for analysts, using the cheapest redundancy that preserves evidence and a lifecycle policy that reduces storage cost over time.

## Implementation notes
- The `verification-docs` container is created with public access disabled.
- Shared Key access is disabled at the storage account level.
- The Web App managed identity can mint user-delegation SAS links for temporary access.
- The access-link endpoint is gated by App Service authentication claims and only accepts the `Analyst` role.
- Analysts use those time-bound links with no account keys involved.
- Storage redundancy is `Standard_LRS`, which is the lowest-cost option that still preserves the evidence in this project scope.
- The lifecycle policy transitions evidence blobs to Cool after 30 days and Archive after 180 days.
- Document names are case-linked by construction: `case_id/<uuid>.<ext>`.

## Acceptance criteria mapping
- Container not publicly accessible: enforced by `--allow-blob-public-access false` and verified with anonymous access denial.
- Analyst access via temporary delegated mechanism: provided by user-delegation SAS.
- Redundancy selected and justified: `LRS` for the project, with `ZRS/GRS` reserved for production discussion.
- Lifecycle policy: enabled in the provisioning script with Cool and Archive transitions.
- Naming convention: upload flow generates names under the case ID and avoids collisions with UUIDs.

## Verification steps
1. Provision the environment with `infra/provision.sh`.
2. Confirm the storage account reports `allowSharedKeyAccess = false`.
3. Attempt anonymous blob access and confirm it is denied.
4. Upload a document through the API and verify the stored blob name includes the case ID.
5. Generate a user-delegation SAS link and confirm the document can be read only while the link is valid.

## Example request
The access-link endpoint expects App Service to inject the authenticated identity in `x-ms-client-principal`. For an Analyst session, the request can look like this:

```bash
curl -sS \
	-H 'x-ms-client-principal: eyJhdXRoX3R5cCI6ImFhZCIsInJvbGVfdHlwIjoicm9sZXMiLCJjbGFpbXMiOlt7InR5cCI6Im5hbWUiLCJ2YWwiOiJhbmFseXN0QGV4YW1wbGUuY29tIn0seyJ0eXAiOiJyb2xlcyIsInZhbCI6IkFuYWx5c3QiXX0=' \
	'https://app-ctn-ingest-dev-<SUFFIX>.azurewebsites.net/cases/case-123/documents/abc123.pdf/access-link?minutes=15'
```

Expected response shape:

```json
{
	"blob": "case-123/abc123.pdf",
	"url": "https://<storage-account>.blob.core.windows.net/verification-docs/case-123/abc123.pdf?<user-delegation-sas>",
	"expires_at": "2026-07-29T12:15:00+00:00",
	"mechanism": "user-delegation-sas"
}
```

## Notes
- The implementation avoids account keys entirely.
- The SAS link is intentionally short-lived so access can be revoked by expiry.
