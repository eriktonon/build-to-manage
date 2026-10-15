import json
import os
import secrets
import time
from datetime import datetime, timezone
from flask import Flask, jsonify, request

APP_NAME = os.getenv("APP_NAME", "service3")
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA", "b2m-carbon-v11")


def resolve_trace_context():
    traceparent = request.headers.get("traceparent") if request else None
    if traceparent and len(traceparent.split("-")) == 4:
        trace_id = traceparent.split("-")[1]
    else:
        trace_id = secrets.token_hex(16)

    span_id = secrets.token_hex(8)

    tx_id = (
        request.headers.get("transactionID")
        or request.headers.get("X-Global-Transaction-Id")
        or request.headers.get("X-Vcap-Request-Id")
        or f"tx-{trace_id[:12]}"
    ) if request else "NoREST"

    return trace_id, span_id, str(tx_id)


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


port = int(os.getenv("PORT", os.getenv("VCAP_APP_PORT", 8082)))
app = Flask(__name__)


@app.route("/service")
def service():
    start = time.perf_counter()
    trace_id, span_id, tx_id = resolve_trace_context()
    simulate_failure = request.args.get("simulate_failure", "false").lower() == "true"
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    if simulate_failure:
        emit_btm_log(
            "ERROR",
            "BTM-LEDGER-5003",
            "Simulated ledger lock contention timeout triggered for FFDC verification",
            trace_id,
            span_id,
            tx_id,
            {"latency_ms": latency_ms},
        )
        return jsonify(
            status="ERROR",
            service=APP_NAME,
            event_code="BTM-LEDGER-5003",
            trace_id=trace_id,
            span_id=span_id,
            transaction_id=tx_id,
            message="Simulated downstream database lock contention",
            runbook_ref="/manage/runbooks/BTM-LEDGER-5003",
        ), 503

    emit_btm_log(
        "INFO",
        "BTM-TRC-3001",
        "Core ledger settlement executed deterministically",
        trace_id,
        span_id,
        tx_id,
        {"latency_ms": latency_ms},
    )
    return jsonify(
        status="SETTLED",
        service=APP_NAME,
        trace_id=trace_id,
        span_id=span_id,
        transaction_id=tx_id,
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
        result="The answer you want — verified with W3C TraceContext & BTM v2.0",
    ), 200


@app.route("/health/live")
@app.route("/health/ready")
def health():
    return jsonify(
        status="UP",
        service=APP_NAME,
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
    ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
