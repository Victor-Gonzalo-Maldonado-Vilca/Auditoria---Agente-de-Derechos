from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents import scenarios  # noqa: E402
from agents.orchestrator import Orchestrator  # noqa: E402

WEB_AVAILABLE = all(
    importlib.util.find_spec(name) for name in ("fastapi", "httpx", "jinja2", "multipart")
)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.orchestrator = Orchestrator(runtime_dir=Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_every_scenario_passes(self):
        catalog = scenarios.load_scenarios()
        self.assertGreaterEqual(len(catalog), 13)
        for result in scenarios.run_all(self.orchestrator, catalog):
            with self.subTest(result["scenario_id"]):
                failed = [item for item in result["checks"] if not item["ok"]]
                self.assertTrue(result["passed"], result["error"] or failed)

    def test_scenario_ids_are_unique(self):
        ids = [item["id"] for item in scenarios.load_scenarios()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_wrong_expectation_is_reported(self):
        scenario = copy.deepcopy(scenarios.load_scenarios()[0])
        scenario["expected"]["status"] = "REVIEW"
        result = scenarios.run_scenario(self.orchestrator, scenario)
        self.assertFalse(result["passed"])
        failed = [item for item in result["checks"] if not item["ok"]]
        self.assertEqual(failed[0]["actual"], "APPROVAL_REQUIRED")

    def test_unexpected_step_error_fails_the_scenario(self):
        scenario = copy.deepcopy(scenarios.load_scenarios()[0])
        scenario["steps"] = ["close"]
        result = scenarios.run_scenario(self.orchestrator, scenario)
        self.assertFalse(result["passed"])
        self.assertIn("Cerrar", result["checks"][-3]["actual"])


@unittest.skipUnless(WEB_AVAILABLE, "Instale requirements.txt y requirements-dev.txt")
class ScenarioWebTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from app.main import create_app

        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(Orchestrator(runtime_dir=Path(self.temp.name))))

    def tearDown(self):
        self.temp.cleanup()

    def test_tab_runs_scenarios(self):
        page = self.client.get("/pruebas").text
        self.assertIn("CP-01", page)
        self.assertIn("Sin ejecutar", page)
        response = self.client.post("/pruebas/ejecutar", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("msg=", response.headers["location"])
        page = self.client.get("/pruebas").text
        self.assertNotIn(">Fallido<", page)
        self.assertIn("Ver caso PRUEBA-CP-01", page)

    def test_api_runs_one_scenario(self):
        body = self.client.post("/api/scenarios/run", params={"scenario_id": "CP-02"}).json()
        self.assertEqual((body["total"], body["passed"]), (1, 1))
        self.assertEqual(len(self.client.get("/api/scenarios").json()), len(scenarios.load_scenarios()))


if __name__ == "__main__":
    unittest.main()
