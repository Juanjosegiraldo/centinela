# Final Cost Report

## Purpose
This document captures the cost evidence required for VOR-52: Final credit report.
It explains how the project stays under the $60 budget and where the main spend occurs.

## Estimated cost profile
- App Service Plan `B1` (Linux): low-tier compute, the largest expected line item.
- Storage Account `Standard_LRS`: minimal storage cost for raw transactions, traces, and documents.
- VNet / NSGs: free.
- Network egress: none expected because all services are internal and storage access is locked down via service endpoint.

### Rough week-3 estimate
- App Service B1: ~ $10–15 per month, prorated for a week = ~$3–4.
- Storage account: < $1 per month for a few MBs of blob storage and queue operations.
- Total expected spend for the lab period: well under $60.

## Actual expense validation
1. In the Azure portal, open Cost Management + Billing.
2. Select the subscription and the period covering the deployment.
3. Filter by resource group `rg-ctn-dev` and review the cost breakdown.
4. Confirm the sum of App Service, Storage, and networking is below $60.

## Evidence to capture
- Screenshot of the cost summary filtered by the project resource group.
- The actual cost number from Azure Cost Management.
- A note on cost drivers: `App Service plan`, `Storage transactions`, `Storage capacity`.

## Conclusion
The target budget is $60; with the chosen architecture and low-volume workload, the design remains comfortably within that limit.
