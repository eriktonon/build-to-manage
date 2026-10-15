import json
import logging
import os
import secrets
import time
import traceback
from datetime import datetime, timezone
from flask import Flask, jsonify, request
import requests

APP_NAME = os.getenv("APP_NAME", "service1")
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA", "b2m-carbon-v11")
SERVICE2_URL = os.getenv("SERVICE2_URL", "http://localhost:8081/service")

FFDC_STORE = []


def resolve_trace_context():
    """Extracts or generates W3C traceparent and X-Global-Transaction-Id."""
    traceparent = request.headers.get("traceparent") if request else None
    if traceparent and len(traceparent.split("-")) == 4:
        parts = traceparent.split("-")
        trace_id = parts[1]
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
    return payload


def capture_ffdc(event_code: str, error_msg: str, trace_id: str, tx_id: str):
    """Practice #10: First Failure Data Capture (FFDC) — snapshots context on first deviation."""
    snapshot = {
        "ffdc_id": f"ffdc-{secrets.token_hex(4)}",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "service": APP_NAME,
        "release": {"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
        "event_code": event_code,
        "trace_id": trace_id,
        "transaction_id": tx_id,
        "downstream_target": SERVICE2_URL,
        "error": error_msg,
        "stack_summary": traceback.format_exc(limit=3),
        "runbook_ref": "/manage/runbooks/BTM-TRC-5001",
    }
    FFDC_STORE.insert(0, snapshot)
    del FFDC_STORE[20:]
    return snapshot


port = int(os.getenv("PORT", os.getenv("VCAP_APP_PORT", 8080)))
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
        "BTM-TRC-1001",
        f"Inbound request accepted at {APP_NAME}; propagating W3C traceparent to service2",
        trace_id,
        span_id,
        tx_id,
    )

    try:
        target_url = f"{SERVICE2_URL}?simulate_failure=true" if simulate_failure else SERVICE2_URL
        resp = requests.get(target_url, headers=headers, timeout=3.0)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        if resp.status_code >= 500:
            ffdc = capture_ffdc("BTM-TRC-5001", f"Downstream service2 returned HTTP {resp.status_code}", trace_id, tx_id)
            emit_btm_log(
                "ERROR",
                "BTM-TRC-5001",
                "Downstream anomaly detected; FFDC snapshot captured automatically",
                trace_id,
                span_id,
                tx_id,
                {"latency_ms": latency_ms, "ffdc_id": ffdc["ffdc_id"]},
            )
            return jsonify(
                status="DEGRADED_FALLBACK",
                service=APP_NAME,
                trace_id=trace_id,
                transaction_id=tx_id,
                ffdc_captured=ffdc,
                downstream_response=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
            ), 502

        emit_btm_log(
            "INFO",
            "BTM-TRC-1002",
            "Correlated response received from service2",
            trace_id,
            span_id,
            tx_id,
            {"latency_ms": latency_ms},
        )
        return jsonify(
            status="OK",
            service=APP_NAME,
            trace_id=trace_id,
            span_id=span_id,
            transaction_id=tx_id,
            latency_ms=latency_ms,
            downstream=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
        ), 200

    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        ffdc = capture_ffdc("BTM-TRC-5001", str(exc), trace_id, tx_id)
        emit_btm_log(
            "ERROR",
            "BTM-TRC-5001",
            f"Downstream call to service2 failed: {exc}",
            trace_id,
            span_id,
            tx_id,
            {"latency_ms": latency_ms, "ffdc_id": ffdc["ffdc_id"]},
        )
        return jsonify(
            status="ERROR",
            service=APP_NAME,
            trace_id=trace_id,
            transaction_id=tx_id,
            ffdc_captured=ffdc,
        ), 503


@app.route("/health/live")
@app.route("/health/ready")
def health():
    return jsonify(
        status="UP",
        service=APP_NAME,
        maturity_level="L4_CASCADING_READY",
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
    ), 200


@app.route("/manage/topology")
def topology():
    return jsonify(
        service=APP_NAME,
        tier="ingress-gateway",
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
        upstream=["api-gateway"],
        downstream=[{"service": "service2", "endpoint": SERVICE2_URL, "protocol": "HTTP/REST + W3C TraceContext"}],
    ), 200


@app.route("/manage/ffdc")
def ffdc_list():
    return jsonify(service=APP_NAME, total_snapshots=len(FFDC_STORE), snapshots=FFDC_STORE), 200


@app.route("/manage/runbooks")
def runbooks():
    return jsonify(
        service=APP_NAME,
        runbooks=[
            {
                "event_code": "BTM-TRC-5001",
                "title": "Downstream Service2 Timeout or 5xx Anomaly",
                "symptom": "HTTP 502/503 on /service with FFDC snapshot emitted.",
                "verification": "Inspect GET /manage/ffdc and verify service2 GET /health/ready.",
                "immediate_action": "Circuit-break downstream retries and route to fallback queue.",
                "cau_escalation_group": "SRE-PLATFORM-TIER2",
            }
        ],
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
