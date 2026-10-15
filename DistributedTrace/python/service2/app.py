import json
import os
import secrets
import time
from datetime import datetime, timezone
from flask import Flask, jsonify, request
import requests

APP_NAME = os.getenv("APP_NAME", "service2")
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA", "b2m-carbon-v11")
SERVICE3_URL = os.getenv("SERVICE3_URL", "http://localhost:8082/service")


def resolve_trace_context():
    traceparent = request.headers.get("traceparent") if request else None
    if traceparent and len(traceparent.split("-")) == 4:
        trace_id = traceparent.split("-")[1]
    else:
        trace_id = secrets.token_hex(16)

    span_id = secrets.token_hex(8)
    new_traceparent = f"00-{trace_id}-{span_id}-01"

    tx_id = (
        request.headers.get("transactionID")
        or request.headers.get("X-Global-Transaction-Id")
        or request.headers.get("X-Vcap-Request-Id")
        or f"tx-{trace_id[:12]}"
    ) if request else "NoREST"

    return trace_id, span_id, new_traceparent, str(tx_id)


def emit_btm_log(severity: str, event_code: str, message: str, trace_id: str, span_id: str, tx_id: str, extra: dict = None):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "service": APP_NAME,
        "release": {"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
        "trace_id": trace_id,
        "span_id": span_id,
        "transaction_id": tx_id,
        "event_code": event_code,
        "message": message,
    }
    if extra:
        payload.update(extra)
    print(json.dumps(payload), flush=True)


port = int(os.getenv("PORT", os.getenv("VCAP_APP_PORT", 8081)))
app = Flask(__name__)


@app.route("/service")
def service():
    start = time.perf_counter()
    trace_id, span_id, traceparent, tx_id = resolve_trace_context()
    simulate_failure = request.args.get("simulate_failure", "false").lower() == "true"

    headers = {
        "traceparent": traceparent,
        "X-Global-Transaction-Id": tx_id,
        "transactionID": tx_id,
    }

    emit_btm_log(
        "INFO",
        "BTM-TRC-2001",
        f"Received correlated request at {APP_NAME}; forwarding to service3",
        trace_id,
        span_id,
        tx_id,
    )

    target_url = f"{SERVICE3_URL}?simulate_failure=true" if simulate_failure else SERVICE3_URL
    resp = requests.get(target_url, headers=headers, timeout=3.0)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    emit_btm_log(
        "INFO" if resp.status_code < 500 else "ERROR",
        "BTM-TRC-2002" if resp.status_code < 500 else "BTM-TRC-5002",
        f"Received response from service3 (HTTP {resp.status_code})",
        trace_id,
        span_id,
        tx_id,
        {"latency_ms": latency_ms},
    )

    return jsonify(
        status="OK" if resp.status_code < 500 else "DOWNSTREAM_ERROR",
        service=APP_NAME,
        trace_id=trace_id,
        span_id=span_id,
        transaction_id=tx_id,
        latency_ms=latency_ms,
        downstream=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
    ), resp.status_code


@app.route("/health/live")
@app.route("/health/ready")
def health():
    return jsonify(
        status="UP",
        service=APP_NAME,
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
    ), 200


@app.route("/manage/topology")
def topology():
    return jsonify(
        service=APP_NAME,
        tier="orchestration-middle-tier",
        upstream=["service1"],
        downstream=[{"service": "service3", "endpoint": SERVICE3_URL}],
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
