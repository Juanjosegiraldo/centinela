# NSG Rules for Centinela

## NSG: `nsg-ctn-app-dev`
| Rule | Direction | Source | Destination | Port(s) | Action | Justification |
|---|---|---|---|---|---|---|
| Allow-App-To-Storage-443 | Outbound | `10.10.1.0/26` | `Storage` service tag | `443` | Allow | API must persist blobs and send queue messages to Azure Storage over TLS.
| Allow-App-To-Data-443 | Outbound | `10.10.1.0/26` | `10.10.2.0/27` | `443` | Allow | App needs secure access to Week 2 data stores in the data subnet.
| Deny-All-Outbound | Outbound | `*` | `*` | `*` | Deny | Explicit deny-by-default for app egress; only listed flows are permitted.

## NSG: `nsg-ctn-data-dev`
| Rule | Direction | Source | Destination | Port(s) | Action | Justification |
|---|---|---|---|---|---|---|
| Allow-Only-AppSubnet-443 | Inbound | `10.10.1.0/26` | `*` | `443` | Allow | Only the app subnet may reach data-layer endpoints on TLS.
| Deny-All-Outbound | Outbound | `*` | `*` | `*` | Deny | Data stores should not initiate outbound traffic.
| Deny-All-Inbound | Inbound | `*` | `*` | `*` | Deny | Default deny-all to prevent unexpected ingress.

## NSG: `nsg-ctn-ops-dev`
| Rule | Direction | Source | Destination | Port(s) | Action | Justification |
|---|---|---|---|---|---|---|
| Deny-All-Inbound | Inbound | `*` | `*` | `*` | Deny | Lock down the operations subnet until specific admin access is added.
| Deny-All-Outbound | Outbound | `*` | `*` | `*` | Deny | Prevent lateral movement and unapproved outbound flows.

## NSG: `nsg-ctn-cache-dev`
| Rule | Direction | Source | Destination | Port(s) | Action | Justification |
|---|---|---|---|---|---|---|
| Deny-All-Inbound | Inbound | `*` | `*` | `*` | Deny | Placeholder subnet is isolated until a concrete cache/workload is added.
| Deny-All-Outbound | Outbound | `*` | `*` | `*` | Deny | No egress until explicit service flows are approved.

## NSG: `nsg-ctn-private-dev`
| Rule | Direction | Source | Destination | Port(s) | Action | Justification |
|---|---|---|---|---|---|---|
| Deny-All-Inbound | Inbound | `*` | `*` | `*` | Deny | Private endpoint subnet should not accept unauthorized traffic.
| Deny-All-Outbound | Outbound | `*` | `*` | `*` | Deny | Private endpoints only communicate via approved network paths.

## Deny-by-default policy
Every NSG includes an explicit deny-all rule at priority `4096`.
No NSG allows traffic from `Any` source except the app outbound flows that are specifically justified.
