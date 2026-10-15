# IBM Build to Manage — Distributed Tracing, Log Correlation & FFDC

This module demonstrates how microservices propagate **W3C TraceContext (`traceparent`)** and **`X-Global-Transaction-Id`** across multi-hop calls (`service1 → service2 → service3`), emitting **Structured JSON Logs** mapped to the **IBM Build to Manage Event Catalog** and triggering **First Failure Data Capture (FFDC)** automatically on the first anomaly.

See [`python/README.md`](python/README.md) for architecture details and execution instructions.
