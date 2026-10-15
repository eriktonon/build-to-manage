# ====================================================================================================
# redishealthcheck.py — IBM Build to Manage Reference (L1-L5 Deep & Synthetic HealthCheck API)
# Modernized for Python 3.12+, OpenShift/Kubernetes, and IBM CSMO Build to Manage v2.0
# LICENSE: MIT (https://opensource.org/licenses/MIT)
# ====================================================================================================
import json
import os
import time
import uuid
from datetime import datetime, timezone
from flask import Flask, jsonify, request
import redis

APP_NAME = os.getenv("APP_NAME", "btm-synthetic-health-service")
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA", "b2m-carbon-v11")
SLO_LATENCY_THRESHOLD_MS = float(os.getenv("SLO_LATENCY_THRESHOLD_MS", "150.0"))


def resolve_redis_uri() -> str:
    if os.environ.get("REDIS_URL"):
        return os.environ["REDIS_URL"]
    if os.environ.get("VCAP_SERVICES"):
        services = json.loads(os.environ["VCAP_SERVICES"])
        for key in ("compose_for_redis", "compose-for-redis", "rediscloud"):
            if key in services and services[key]:
                return str(services[key][0]["credentials"]["uri"])
    return "redis://localhost:6379/0"


REDIS_URI = resolve_redis_uri()
client = redis.from_url(REDIS_URI, socket_connect_timeout=2, socket_timeout=2)

port = int(os.getenv("PORT", os.getenv("VCAP_APP_PORT", 8080)))
app = Flask(__name__)


def check_redis_dependency(run_synthetic: bool = False) -> dict:
    """Executes L3 (connectivity) or L5 (synthetic non-destructive read/write probe) check."""
    start = time.perf_counter()
    try:
        if run_synthetic:
            probe_key = f"btm:synthetic:probe:{uuid.uuid4().hex[:8]}"
            client.setex(probe_key, 5, "OK")
            val = client.get(probe_key)
            client.delete(probe_key)
            if val not in (b"OK", "OK"):
                raise RuntimeError("Synthetic read-after-write verification mismatch")
        else:
            client.ping()

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        status = "DEGRADED" if latency_ms > SLO_LATENCY_THRESHOLD_MS else "UP"
        return {
            "name": "redis-state-store",
            "level": "L5_SYNTHETIC" if run_synthetic else "L3_DIRECT",
            "status": status,
            "latency_ms": latency_ms,
            "slo_threshold_ms": SLO_LATENCY_THRESHOLD_MS,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "name": "redis-state-store",
            "level": "L5_SYNTHETIC" if run_synthetic else "L3_DIRECT",
            "status": "DOWN",
            "latency_ms": latency_ms,
            "error_code": "BTM-HC-5002",
            "message": str(exc),
            "runbook_ref": "/manage/runbooks/BTM-HC-5002",
        }


@app.route("/health/live")
def liveness():
    return jsonify(
        status="UP",
        maturity_level="L1_LIVENESS",
        service=APP_NAME,
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
        timestamp=datetime.now(timezone.utc).isoformat(),
    ), 200


@app.route("/health/ready")
@app.route("/health/deep")
@app.route("/healthcheck")
def deep_healthcheck():
    synthetic = request.args.get("synthetic", "false").lower() == "true"
    redis_check = check_redis_dependency(run_synthetic=synthetic)
    overall_status = redis_check["status"]
    http_code = 200 if overall_status in ("UP", "DEGRADED") else 503

    return jsonify(
        status=overall_status,
        maturity_level="L5_SYNTHETIC_TRANSACTION" if synthetic else "L4_DEEP_DEPENDENCY",
        service=APP_NAME,
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=[redis_check],
    ), http_code


@app.route("/")
def root():
    return jsonify(
        service=APP_NAME,
        framework="IBM Build to Manage v2.0 (L1-L5 HealthCheck API)",
        endpoints=[
            "/health/live",
            "/health/ready",
            "/health/deep",
            "/health/deep?synthetic=true",
        ],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
