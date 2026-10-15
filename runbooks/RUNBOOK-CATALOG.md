# IBM Build to Manage — Executable Runbook Catalog (Practice #09)

In the **IBM CSMO Build to Manage** model, no alert or error code (`BTM-*`) can exist in production without a deterministic **Runbook** mapped to a specific **CAU Group (Owner / Escalation Squad)** and linked to **First Failure Data Capture (FFDC)**.

---

## `BTM-HC-5001` — Backing Store Readiness Probe Failure (L3)

- **Severity**: `CRITICAL` (HTTP `503 Service Unavailable` on `/health/ready`)
- **CAU Escalation Group**: `SRE-DATASTORE-OPS`
- **Symptom**: Kubernetes removes pod from `Service` endpoints; readiness probe returns `BTM-HC-5001`.
- **How to Verify (Deterministic Check)**:
  ```bash
  curl -s http://localhost:8080/health/ready | jq .
  ```
- **Probable Cause**: Redis/Database connection pool exhaustion, network policy rotation, or credential expiry.
- **Immediate Automated Remediation**:
  1. Keep `livenessProbe` (`/health/live`) returning `200 OK` to prevent cascading pod restart storms while isolating traffic via `readinessProbe`.
  2. Rotate connection pool and verify Redis primary replica health.
- **Post-Remediation Validation**: Confirm 3 consecutive `200 OK` responses on `/health/deep?synthetic=true` with `latency_ms < 50ms`.

---

## `BTM-HC-5002` — Synthetic Transaction Latency Breach (L5)

- **Severity**: `WARNING` (`status: DEGRADED`)
- **CAU Escalation Group**: `SRE-PLATFORM-TIER2`
- **Symptom**: `/health/deep?synthetic=true` succeeds functionally but `latency_ms > 150ms` (SLO threshold).
- **How to Verify**:
  ```bash
  curl -s "http://localhost:8080/health/deep?synthetic=true" | jq .checks
  ```
- **Immediate Automated Remediation**:
  1. Block automated Canary promotion in the Delivery Pipeline (Telemetry Gate).
  2. Inspect memory saturation and slowlog on the state store.

---

## `BTM-TRC-5001` — Downstream Distributed Trace Failure & FFDC Trigger

- **Severity**: `ERROR` (HTTP `502/503`)
- **CAU Escalation Group**: `SRE-PLATFORM-TIER2`
- **Symptom**: `service1` receives an upstream error or timeout from `service2` and emits an automated **FFDC Snapshot** (`ffdc-*`).
- **How to Verify (Zero Bug-Repro Needed)**:
  ```bash
  curl -s http://localhost:8080/manage/ffdc | jq '.snapshots[0]'
  ```
- **Immediate Automated Remediation**:
  1. Read the `trace_id` and `transaction_id` directly from the FFDC snapshot.
  2. Open Circuit Breaker for downstream hop and serve degraded fallback response.

---

## `BTM-LEDGER-5003` — Core Ledger Lock Contention Timeout

- **Severity**: `CRITICAL`
- **CAU Escalation Group**: `CORE-LEDGER-SQUAD`
- **Symptom**: `service3` aborts transaction due to lock wait timeout exceeding budget.
- **Immediate Automated Remediation**:
  1. Enforce idempotency key (`transaction_id`) deduplication before retry.
  2. Route payload to dead-letter / async settlement outbox for safe replay.
