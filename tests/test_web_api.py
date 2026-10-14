from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WEB_AVAILABLE = all(
    importlib.util.find_spec(name) for name in ("fastapi", "httpx", "jinja2", "multipart")
)


@unittest.skipUnless(WEB_AVAILABLE, "Instale requirements.txt y requirements-dev.txt")
class WebApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from agents.orchestrator import Orchestrator
        from app.main import create_app

        self.temp = tempfile.TemporaryDirectory()
        orchestrator = Orchestrator(runtime_dir=Path(self.temp.name))
        self.client = TestClient(create_app(orchestrator))

    def tearDown(self):
        self.temp.cleanup()

    def create(self, **overrides):
        payload = {
            "request_id": "DSAR-API-1",
            "principal_id": "person-001",
            "request_type": "erasure",
            "policy_id": "LAB-30",
            "request_text": "Solicito la eliminacion de mis datos.",
            "identity_verification": {"status": "verified", "reference": "ref-1"},
        }
        payload.update(overrides)
        return self.client.post("/api/requests", json=payload)

    def test_full_flow_through_api(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["available_actions"], ["approve", "reject"])
        decision = {"approver": "Ana", "role": "DPO", "comment": "Procede"}
        self.assertEqual(
            self.client.post("/api/cases/DSAR-API-1/approve", json=decision).json()["status"],
            "APPROVED",
        )
        for step in ("fulfill", "send", "close"):
            response = self.client.post(f"/api/cases/DSAR-API-1/{step}", json={"actor": "Ana"})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "CLOSED")
        markdown = self.client.get("/api/cases/DSAR-API-1/response.md")
        self.assertIn("Respuesta DSAR", markdown.text)
        self.assertTrue(self.client.get("/api/evidence/verify").json()["valid"])

    def test_invalid_transition_returns_409(self):
        self.create()
        response = self.client.post("/api/cases/DSAR-API-1/fulfill", json={"actor": "Ana"})
        self.assertEqual(response.status_code, 409)

    def test_invalid_input_and_unknown_case(self):
        self.assertEqual(self.create(policy_id="NO-EXISTE").status_code, 422)
        self.assertEqual(self.create(request_type="otro").status_code, 422)
        self.assertEqual(self.client.get("/api/cases/NO-EXISTE").status_code, 404)

    def test_html_pages_and_form_flow(self):
        for path in ("/", "/solicitudes/nueva", "/evidencia", "/inventario"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        response = self.client.post(
            "/solicitudes",
            data={
                "request_type": "access",
                "principal_id": "person-002",
                "policy_id": "LAB-30",
                "request_text": "<script>alert(1)</script>",
                "identity_verified": "on",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        case_url = response.headers["location"].split("?")[0]
        page = self.client.get(case_url)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", page.text)
        response = self.client.post(
            f"{case_url}/approve",
            data={"actor": "Ana", "role": "DPO", "comment": "ok"},
            follow_redirects=False,
        )
        self.assertIn("msg=", response.headers["location"])
        self.assertEqual(self.client.get("/casos/NO-EXISTE").status_code, 404)


if __name__ == "__main__":
    unittest.main()
