# Distributed Trace, Structured JSON Log Catalog & FFDC in Python

Reference implementation of **IBM Build to Manage** Practices **#02 (Log Format & Catalog)**, **#04 (Deployment Correlation)**, **#05 (Distributed Tracing — W3C TraceContext)**, **#06 (Topology Information)**, **#09 (Runbooks as Code)**, and **#10 (First Failure Data Capture — FFDC)** across a 3-tier microservice chain (`service1 → service2 → service3`).

---

## Structured JSON Log Output (IBM Build to Manage v2.0 Standard)

Instead of unstructured plain text strings, every log record is emitted as a single-line JSON document carrying W3C trace correlation, release metadata, and a deterministic `event_code`:

```json
{"timestamp":"2026-10-15T12:00:01.104Z","severity":"INFO","service":"service1","release":{"version":"2.0.0","commit_sha":"b2m-carbon-v11"},"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","transaction_id":"tx-4bf92f3577b3","event_code":"BTM-TRC-1001","message":"Inbound request accepted at ingress; propagating W3C traceparent to service2","latency_ms":14.2}
{"timestamp":"2026-10-15T12:00:01.112Z","severity":"INFO","service":"service2","release":{"version":"2.0.0","commit_sha":"b2m-carbon-v11"},"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"a91c44e8210f33c1","transaction_id":"tx-4bf92f3577b3","event_code":"BTM-TRC-2001","message":"Forwarding correlated transaction to downstream ledger service3","latency_ms":6.8}
{"timestamp":"2026-10-15T12:00:01.116Z","severity":"INFO","service":"service3","release":{"version":"2.0.0","commit_sha":"b2m-carbon-v11"},"trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"f812b039d71044e2","transaction_id":"tx-4bf92f3577b3","event_code":"BTM-TRC-3001","message":"Core ledger settlement executed deterministically","latency_ms":2.1}
```

---

## Standard Manageability Endpoints Exposed by Every Service

| Endpoint | BTM Practice | Purpose |
| :--- | :--- | :--- |
| `GET /service` | **#05 Distributed Tracing** | Executes the `service1 → service2 → service3` chain with W3C `traceparent` propagation. Pass `?simulate_failure=true` to trigger an anomaly and FFDC capture. |
| `GET /health/live` & `/health/ready` | **#01 HealthCheck API** | Liveness and Readiness probes with release correlation. |
| `GET /manage/topology` | **#06 Topology Information** | Self-declared upstream/downstream dependency graph JSON. |
| `GET /manage/ffdc` | **#10 First Failure Data Capture** | Returns sanitized diagnostic snapshots captured at the exact millisecond of the first failure (no bug reproduction required). |
| `GET /manage/runbooks` | **#09 Runbooks as Code** | Returns machine- and human-readable remediation steps mapped to `event_code`. |

---

## Running Locally (Docker Compose or Python 3.12+)

### Option A: Docker Compose (From Repository Root)
```bash
docker compose up --build
```

### Option B: Direct Python Execution
```bash
# Terminal 1 (Service 3 - port 8082)
PORT=8082 python service3/app.py

# Terminal 2 (Service 2 - port 8081)
PORT=8081 SERVICE3_URL=http://localhost:8082/service python service2/app.py

# Terminal 3 (Service 1 - port 8080)
PORT=8080 SERVICE2_URL=http://localhost:8081/service python service1/app.py
```

Trigger a normal correlated trace:
```bash
curl -s http://localhost:8080/service | jq .
```

Trigger a simulated downstream failure and inspect the captured **FFDC Snapshot**:
```bash
curl -s "http://localhost:8080/service?simulate_failure=true" | jq .
curl -s http://localhost:8080/manage/ffdc | jq .
```
