# Centinela Network Topology

## Overview
This topology is sized for Week 3 scaling and isolates data stores deployed in Week 2 on an already-isolated network.

## VNet and Subnets
| Subnet | CIDR | Purpose | Components |
|---|---|---|---|
| `snet-app` | `10.10.1.0/26` | App service integration | App Service (API), future functions, app-managed resources | 
| `snet-data` | `10.10.2.0/27` | Data platform isolation | Week 2 SQL, Cosmos DB and future stateful stores | 
| `snet-ops` | `10.10.3.0/27` | Operational access | Bastion/jumpbox or admin tools, restricted management traffic | 
| `snet-cache` | `10.10.4.0/27` | Week 3 placeholder | Cache, shared services, analytics agents | 
| `snet-private` | `10.10.5.0/27` | Private endpoints | Private endpoint-backed services, future siloed workloads |

## Sizing justification
- `snet-app` uses `/26` for up to 59 usable IPs.
- App Service VNet integration requires at least `/28`; `/26` supports Week 3 scaling for additional app slots, functions, and service endpoints.
- `snet-data`, `snet-ops`, `snet-cache`, and `snet-private` each use `/27` for up to 29 usable IPs, sufficient for enclosed service clusters and future growth.

## Traffic isolation
- App subnet has a dedicated NSG `nsg-ctn-app-dev`.
- Data subnet has `nsg-ctn-data-dev` with inbound allow only from `snet-app` and deny-by-default.
- Ops, Cache, and Private subnets each have their own NSGs.

## Future components
- `snet-cache`: Redis Cache, search, external ingestion proxies.
- `snet-private`: private endpoints for Storage, SQL, Cosmos, Service Bus, Key Vault; API access only through the app subnet.
