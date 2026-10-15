import json
from pathlib import Path
import py_compile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class TestBuildToManageContracts(unittest.TestCase):
    def test_python_sources_compile_cleanly(self):
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

    def test_event_catalog_schema(self):
        catalog_path = ROOT / "catalog/event-and-log-catalog.json"
        self.assertTrue(catalog_path.exists())
        data = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertIn("required_log_fields", data)
        self.assertIn("trace_id", data["required_log_fields"])
        self.assertIn("event_code", data["required_log_fields"])
        self.assertGreaterEqual(len(data["events"]), 5)

    def test_runbooks_and_carbon_console_exist(self):
        runbook_path = ROOT / "runbooks/RUNBOOK-CATALOG.md"
        console_path = ROOT / "docs/index.html"
        diagram_path = ROOT / "BTM.png"
        self.assertTrue(runbook_path.exists())
        self.assertTrue(console_path.exists())
        self.assertTrue(diagram_path.exists())
        self.assertIn("BTM-TRC-5001", runbook_path.read_text(encoding="utf-8"))
        self.assertIn("#0f62fe", console_path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
