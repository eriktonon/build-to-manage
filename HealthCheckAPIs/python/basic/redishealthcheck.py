# ====================================================================================================
# redishealthcheck.py — IBM Build to Manage Reference (Basic L1-L3 HealthCheck API)
# Modernized for Python 3.12+, Kubernetes/OpenShift, and IBM CSMO Build to Manage v2.0
# LICENSE: MIT (https://opensource.org/licenses/MIT)
# ====================================================================================================
import json
import os
import time
from datetime import datetime, timezone
from flask import Flask, jsonify
import redis

APP_NAME = os.getenv("APP_NAME", "btm-redis-health-service")
APP_VERSION = os.getenv("APP_VERSION", "2.0.0")
GIT_COMMIT_SHA = os.getenv("GIT_COMMIT_SHA", "b2m-carbon-v11")


def resolve_redis_uri() -> str:
    """Resolve Redis URI from standard cloud-native env vars or legacy VCAP_SERVICES."""
    if os.environ.get("REDIS_URL"):
        return os.environ["REDIS_URL"]
    if os.environ.get("VCAP_SERVICES"):
        services = json.loads(os.environ["VCAP_SERVICES"])
        for key in ("compose-for-redis", "compose_for_redis", "rediscloud"):
            if key in services and services[key]:
                return str(services[key][0]["credentials"]["uri"])
    return "redis://localhost:6379/0"


REDIS_URI = resolve_redis_uri()
client = redis.from_url(REDIS_URI, socket_connect_timeout=2, socket_timeout=2)

port = int(os.getenv("PORT", os.getenv("VCAP_APP_PORT", 8080)))
app = Flask(__name__)


@app.route("/health/live")
def liveness():
    """L1/L2 Liveness Probe: verifies process is alive and event loop is responsive."""
    return jsonify(
        status="UP",
        maturity_level="L1_LIVENESS",
        service=APP_NAME,
        release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
        timestamp=datetime.now(timezone.utc).isoformat(),
    ), 200


@app.route("/health/ready")
@app.route("/healthcheck")
def healthcheck():
    """L3 Readiness Probe: verifies connectivity and latency to Redis backing store."""
    start = time.perf_counter()
    try:
        client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return jsonify(
            status="UP",
            maturity_level="L3_DEPENDENCY_PROBE",
            service=APP_NAME,
            release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
            timestamp=datetime.now(timezone.utc).isoformat(),
            dependencies=[
                {
                    "name": "redis-cache",
                    "type": "datastore",
                    "status": "UP",
                    "latency_ms": latency_ms,
                }
            ],
        ), 200
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return jsonify(
            status="DOWN",
            maturity_level="L3_DEPENDENCY_PROBE",
            service=APP_NAME,
            release={"version": APP_VERSION, "commit_sha": GIT_COMMIT_SHA},
            timestamp=datetime.now(timezone.utc).isoformat(),
            error_code="BTM-HC-5001",
            runbook_ref="/manage/runbooks/BTM-HC-5001",
            dependencies=[
                {
                    "name": "redis-cache",
                    "type": "datastore",
                    "status": "DOWN",
                    "latency_ms": latency_ms,
                    "error": str(exc),
                }
            ],
        ), 503


@app.route("/")
def root():
    return jsonify(
        service=APP_NAME,
        framework="IBM Build to Manage v2.0",
        endpoints=["/health/live", "/health/ready", "/healthcheck"],
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
