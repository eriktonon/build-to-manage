import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import py_compile
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import MagicMock, patch
import requests

ROOT = Path(__file__).resolve().parent.parent


def load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_http_ready(url: str, timeout_sec: float = 10.0):
    deadline = time.time() + timeout_sec
    last_err = None
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=1.0)
            if r.status_code == 200:
                return r
        except Exception as exc:
            last_err = exc
        time.sleep(0.15)
    raise RuntimeError(f"Service at {url} did not become ready in {timeout_sec}s (last error: {last_err})")


class TestBuildToManageEndToEnd(unittest.TestCase):
    """Real functional & integration tests for all IBM Build to Manage v2.0 applications."""

    def test_01_python_sources_compile_cleanly(self):
        py_files = [
            ROOT / "HealthCheckAPIs/python/basic/redishealthcheck.py",
            ROOT / "HealthCheckAPIs/python/frameworks/redishealthcheck.py",
            ROOT / "DistributedTrace/python/service1/app.py",
            ROOT / "DistributedTrace/python/service2/app.py",
            ROOT / "DistributedTrace/python/service3/app.py",
            ROOT / "DistributedTrace/python/service3/logtest.py",
        ]
        for path in py_files:
            self.assertTrue(path.exists(), f"Missing file: {path}")
            py_compile.compile(str(path), doraise=True)

    def test_02_basic_redis_healthcheck_l1_and_l3(self):
        """Tests HealthCheckAPIs/python/basic/redishealthcheck.py with simulated UP and DOWN states."""
        basic_mod = load_module_from_path(
            "basic_redishealthcheck",
            ROOT / "HealthCheckAPIs/python/basic/redishealthcheck.py",
        )
        client = basic_mod.app.test_client()

        # 1. L1 Liveness Probe must always return 200 UP
        res_live = client.get("/health/live")
        self.assertEqual(res_live.status_code, 200)
        body_live = res_live.get_json()
        self.assertEqual(body_live["status"], "UP")
        self.assertEqual(body_live["maturity_level"], "L1_LIVENESS")

        # 2. L3 Readiness Probe when Redis is UP
        with patch.object(basic_mod.client, "ping", return_value=True):
            res_ready = client.get("/health/ready")
            self.assertEqual(res_ready.status_code, 200)
            body_ready = res_ready.get_json()
            self.assertEqual(body_ready["status"], "UP")
            self.assertEqual(body_ready["maturity_level"], "L3_DEPENDENCY_PROBE")
            self.assertEqual(body_ready["dependencies"][0]["status"], "UP")

        # 3. L3 Readiness Probe when Redis is DOWN -> HTTP 503 + BTM-HC-5001 + Runbook Ref
        with patch.object(basic_mod.client, "ping", side_effect=ConnectionError("Redis connection refused")):
            res_down = client.get("/healthcheck")
            self.assertEqual(res_down.status_code, 503)
            body_down = res_down.get_json()
            self.assertEqual(body_down["status"], "DOWN")
            self.assertEqual(body_down["error_code"], "BTM-HC-5001")
            self.assertEqual(body_down["runbook_ref"], "/manage/runbooks/BTM-HC-5001")

    def test_03_frameworks_redis_healthcheck_l1_to_l5_synthetic(self):
        """Tests HealthCheckAPIs/python/frameworks/redishealthcheck.py L1, L3, and L5 Synthetic Probe."""
        fw_mod = load_module_from_path(
            "fw_redishealthcheck",
            ROOT / "HealthCheckAPIs/python/frameworks/redishealthcheck.py",
        )
        client = fw_mod.app.test_client()

        # 1. L5 Synthetic Transaction Probe (SETEX -> GET -> DELETE verification)
        with patch.object(fw_mod.client, "setex", return_value=True) as mock_setex, \
             patch.object(fw_mod.client, "get", return_value=b"OK") as mock_get, \
             patch.object(fw_mod.client, "delete", return_value=1) as mock_del:
            res_syn = client.get("/health/deep?synthetic=true")
            self.assertEqual(res_syn.status_code, 200)
            body_syn = res_syn.get_json()
            self.assertEqual(body_syn["status"], "UP")
            self.assertEqual(body_syn["maturity_level"], "L5_SYNTHETIC_TRANSACTION")
            self.assertEqual(body_syn["checks"][0]["level"], "L5_SYNTHETIC")
            mock_setex.assert_called_once()
            mock_get.assert_called_once()
            mock_del.assert_called_once()

        # 2. L5 Synthetic Transaction Mismatch / Failure -> HTTP 503 + BTM-HC-5002
        with patch.object(fw_mod.client, "setex", return_value=True), \
             patch.object(fw_mod.client, "get", return_value=b"CORRUPTED"), \
             patch.object(fw_mod.client, "delete", return_value=1):
            res_fail = client.get("/health/deep?synthetic=true")
            self.assertEqual(res_fail.status_code, 503)
            body_fail = res_fail.get_json()
            self.assertEqual(body_fail["status"], "DOWN")
            self.assertEqual(body_fail["checks"][0]["error_code"], "BTM-HC-5002")

    def test_04_structured_json_logger_filter(self):
        """Tests DistributedTrace/python/service3/logtest.py JSON log formatting."""
        log_mod = load_module_from_path(
            "service3_logtest",
            ROOT / "DistributedTrace/python/service3/logtest.py",
        )
        stream = io.StringIO()
        logger = logging.getLogger("btm.test.logger")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(stream)
        handler.setFormatter(log_mod.BTMJsonFormatter())
        logger.addHandler(handler)
        logger.addFilter(log_mod.TransactionIDContextFilter())

        logger.info("Verification log message")
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        self.assertEqual(parsed["severity"], "INFO")
        self.assertEqual(parsed["service"], "btm.test.logger")
        self.assertEqual(parsed["event_code"], "BTM-LOG-1000")
        self.assertIn("trace_id", parsed)
        self.assertIn("transaction_id", parsed)

    def test_05_live_distributed_trace_w3c_and_ffdc_across_3_microservices(self):
        """Spawns real service1, service2, and service3 processes and verifies W3C TraceContext & FFDC."""
        port3 = find_free_port()
        port2 = find_free_port()
        port1 = find_free_port()

        env3 = {**os.environ, "PORT": str(port3), "APP_NAME": "service3"}
        env2 = {
            **os.environ,
            "PORT": str(port2),
            "APP_NAME": "service2",
            "SERVICE3_URL": f"http://127.0.0.1:{port3}/service",
        }
        env1 = {
            **os.environ,
            "PORT": str(port1),
            "APP_NAME": "service1",
            "SERVICE2_URL": f"http://127.0.0.1:{port2}/service",
        }

        proc3 = subprocess.Popen(
            [sys.executable, str(ROOT / "DistributedTrace/python/service3/app.py")],
            env=env3,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc2 = subprocess.Popen(
            [sys.executable, str(ROOT / "DistributedTrace/python/service2/app.py")],
            env=env2,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc1 = subprocess.Popen(
            [sys.executable, str(ROOT / "DistributedTrace/python/service1/app.py")],
            env=env1,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            wait_for_http_ready(f"http://127.0.0.1:{port3}/health/ready")
            wait_for_http_ready(f"http://127.0.0.1:{port2}/health/ready")
            wait_for_http_ready(f"http://127.0.0.1:{port1}/health/ready")

            # A) Verify End-to-End W3C TraceContext Propagation (service1 -> service2 -> service3)
            custom_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
            custom_tx_id = "tx-btm-e2e-verification-001"
            headers = {
                "traceparent": f"00-{custom_trace_id}-00f067aa0ba902b7-01",
                "X-Global-Transaction-Id": custom_tx_id,
            }
            resp_ok = requests.get(f"http://127.0.0.1:{port1}/service", headers=headers, timeout=5.0)
            self.assertEqual(resp_ok.status_code, 200)
            data_ok = resp_ok.json()
            self.assertEqual(data_ok["status"], "OK")
            self.assertEqual(data_ok["trace_id"], custom_trace_id)
            self.assertEqual(data_ok["transaction_id"], custom_tx_id)
            # Verify service2 and service3 received the exact same trace_id and transaction_id
            hop2 = data_ok["downstream"]
            self.assertEqual(hop2["service"], "service2")
            self.assertEqual(hop2["trace_id"], custom_trace_id)
            self.assertEqual(hop2["transaction_id"], custom_tx_id)
            hop3 = hop2["downstream"]
            self.assertEqual(hop3["service"], "service3")
            self.assertEqual(hop3["status"], "SETTLED")
            self.assertEqual(hop3["trace_id"], custom_trace_id)
            self.assertEqual(hop3["transaction_id"], custom_tx_id)

            # B) Verify Simulated Downstream Anomaly Triggers Automatic FFDC Snapshot on Service1
            resp_err = requests.get(
                f"http://127.0.0.1:{port1}/service?simulate_failure=true",
                headers=headers,
                timeout=5.0,
            )
            self.assertEqual(resp_err.status_code, 502)
            data_err = resp_err.json()
            self.assertEqual(data_err["status"], "DEGRADED_FALLBACK")
            self.assertIn("ffdc_captured", data_err)
            ffdc_id = data_err["ffdc_captured"]["ffdc_id"]

            # Query /manage/ffdc endpoint on service1 to verify the snapshot was persisted
            resp_ffdc = requests.get(f"http://127.0.0.1:{port1}/manage/ffdc", timeout=3.0)
            self.assertEqual(resp_ffdc.status_code, 200)
            ffdc_list = resp_ffdc.json()
            self.assertGreaterEqual(ffdc_list["total_snapshots"], 1)
            self.assertEqual(ffdc_list["snapshots"][0]["ffdc_id"], ffdc_id)
            self.assertEqual(ffdc_list["snapshots"][0]["event_code"], "BTM-TRC-5001")
            self.assertEqual(ffdc_list["snapshots"][0]["trace_id"], custom_trace_id)

            # C) Verify /manage/topology and /manage/runbooks endpoints
            resp_topo = requests.get(f"http://127.0.0.1:{port1}/manage/topology", timeout=3.0)
            self.assertEqual(resp_topo.status_code, 200)
            self.assertEqual(resp_topo.json()["downstream"][0]["service"], "service2")

            resp_rb = requests.get(f"http://127.0.0.1:{port1}/manage/runbooks", timeout=3.0)
            self.assertEqual(resp_rb.status_code, 200)
            self.assertEqual(resp_rb.json()["runbooks"][0]["cau_escalation_group"], "SRE-PLATFORM-TIER2")

        finally:
            for p in (proc1, proc2, proc3):
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()

    def test_06_event_catalog_and_carbon_assets(self):
        catalog_path = ROOT / "catalog/event-and-log-catalog.json"
        runbook_path = ROOT / "runbooks/RUNBOOK-CATALOG.md"
        console_path = ROOT / "docs/index.html"
        diagram_path = ROOT / "BTM.png"

        self.assertTrue(catalog_path.exists())
        self.assertTrue(runbook_path.exists())
        self.assertTrue(console_path.exists())
        self.assertTrue(diagram_path.exists())

        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertIn("required_log_fields", data)
        self.assertIn("trace_id", data["required_log_fields"])
        self.assertIn("event_code", data["required_log_fields"])
        self.assertGreaterEqual(len(data["events"]), 5)


if __name__ == "__main__":
    unittest.main()
