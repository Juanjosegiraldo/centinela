# Deliverable W2-05 — Migrate Secrets to Key Vault

Owner: Miguel
Maps to: W2-05

## Goal
Keep every credential out of code and version history, and access secrets only through managed identity.

## Strategy
- The application code does not store passwords, keys, or connection strings inline.
- Azure services are accessed with `DefaultAzureCredential`, so the Web App and Function authenticate through managed identity.
- Sensitive values are written into Key Vault during provisioning and later read by the platform identity.

## Secret names in use
- `sql-connection-string`
- `cosmos-endpoint`
- `servicebus-fqdn`
- `score-threshold`

## Acceptance criteria mapping
- No credentials in code: satisfied by the current codebase.
- No credentials in repository or git history: verified with a git audit before merge.
- Components authenticate with managed identity: satisfied by the Web App and Function identities.

## Evidence to attach
- Secret names list from Key Vault provisioning.
- Git audit output showing no credential literals in history. The audit command returned no matches.

## Notes
- `score-threshold` is an operational configuration value, not a credential, but it is still stored in Key Vault to avoid redeploys.
- This document records the decision; the actual secret provisioning remains in `infra/provision-week2.sh`.