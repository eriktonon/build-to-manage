# IBM Build to Manage — HealthCheck API Reference (L1 to L5 Maturity)

In the **IBM Build to Manage (CSMO / SRE)** framework, a HealthCheck API is not just a static `200 OK` ping. It is the primary contract between the **Managed Entity (Microservice)** and the **Management System (Kubernetes/OpenShift, Load Balancers, and AIOps)**.

## The 5 Maturity Levels of IBM HealthCheck APIs

| Level | Maturity Name | Endpoint | Operational Verification | Consumers |
| :---: | :--- | :--- | :--- | :--- |
| **L1** | **Basic HTTP Liveness** | `GET /health/live` | Confirms the runtime process and HTTP listener are responsive. | Kubernetes `livenessProbe` |
| **L2** | **Local Resource Health** | `GET /health/live` | Checks local memory, file descriptors, and thread pool non-exhaustion. | Container Runtime |
| **L3** | **Direct Dependency Probe** | `GET /health/ready` | Verifies active connectivity to critical dependencies (Redis, DB, Kafka). | Kubernetes `readinessProbe` / Ingress |
| **L4** | **Cascading Dependency Health** | `GET /health/deep` | Queries downstream microservice health endpoints and aggregates latency/status. | Service Mesh / SRE Dashboard |
| **L5** | **Synthetic Business Transaction** | `GET /health/deep?synthetic=true` | Executes a non-destructive synthetic read/write probe with correlation ID. | AIOps / Canary Telemetry Gate |

---

## Structure

- **[`basic/`](basic/)**: Lightweight zero-framework dependency implementation in Python 3 (`Flask` + `redis`) exposing `/health/live`, `/health/ready`, and `/healthcheck` with **Deployment Correlation** (`version`, `commit_sha`) and structured JSON output.
- **[`frameworks/`](frameworks/)**: Full **L1–L5 IBM Build to Manage HealthCheck** implementation including **Synthetic Transaction verification (L5)**, per-dependency latency telemetry, and **First Failure Data Capture (FFDC)** hook when a dependency transitions to `DOWN`.

---

## Running Locally

```bash
pip install -r frameworks/requirements.txt
python frameworks/redishealthcheck.py
```

Query the endpoints:
```bash
curl -s http://localhost:8080/health/live | jq .
curl -s http://localhost:8080/health/ready | jq .
curl -s "http://localhost:8080/health/deep?synthetic=true" | jq .
```