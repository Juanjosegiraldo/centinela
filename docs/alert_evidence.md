# Alert Configuration and Proof

## Goal
Document a real alert and prove it fires under a controlled failure condition.

## Alert design
- Condition: CPU or request latency on the App Service exceeds a safe threshold.
- Justification: The API is business-critical and must not silently fail.
- Threshold: set a value that is reachable in the lab under load while remaining meaningful.

## Recommended alert
- Platform: Azure Monitor alert rule for App Service.
- Metric: `Requests/Latency` or `CpuTime`.
- Scope: the deployed App Service.
- Condition: `Average` metric > `2000 ms` for `5 minutes`.
- Action: email to the team or webhook to the operations channel.

## Proof procedure
1. Deploy the App Service and enable Application Insights if not already enabled.
2. Create the alert rule in Azure Monitor.
3. Generate traffic using `tools/send_transactions.py` or a load script.
4. If needed, send a batch of high-latency requests or introduce a deliberate delay.
5. Confirm the alert fires and capture the incident screenshot.

## Evidence to capture
- Screenshot of the alert rule settings.
- Timestamped alert notification or action log.
- Description of the simulated condition and the observed result.

## Notes
This document provides the evidence path for VOR-51 and supports the project closure validation.
