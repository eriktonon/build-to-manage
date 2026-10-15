# Contributing to Build to Manage (BTM) Reference Architecture

We welcome contributions that expand or refine the **11 Canonical Build to Manage Practices** across cloud-native runtimes (Python, Rust, Go, Node.js, Java/Quarkus, Kubernetes, and OpenShift).

---

## Core Contribution Principles

1. **Shift-Left Operability**: Every sample microservice added to this repository must expose at minimum:
   - L1–L5 HealthCheck endpoints (`/health/live`, `/health/ready`, `/health/deep`)
   - Structured single-line JSON logs conforming to [`catalog/event-and-log-catalog.json`](catalog/event-and-log-catalog.json)
   - W3C `traceparent` + `X-Global-Transaction-Id` propagation
   - Deployment correlation metadata (`release.version`, `release.commit_sha`)
   - First Failure Data Capture (FFDC) hook mapped to a Runbook in [`runbooks/RUNBOOK-CATALOG.md`](runbooks/RUNBOOK-CATALOG.md)
2. **IBM Carbon Design System v11 Compliance**: UI dashboards and architectural diagrams must adhere strictly to **IBM Carbon v11** tokens (`#0F62FE` IBM Blue 60, `#161616` Carbon Gray 100, `IBM Plex Sans`, `IBM Plex Mono`, `0px` corners, and `1px` hairline grid).
3. **Deterministic Verification**: All Pull Requests are automatically verified by GitHub Actions ([`.github/workflows/btm-verification.yml`](.github/workflows/btm-verification.yml)).

---

## Local Verification Before Submitting a PR

Run the contract and syntax verification suite locally:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
