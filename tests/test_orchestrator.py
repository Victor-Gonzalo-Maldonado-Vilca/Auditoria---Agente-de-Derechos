from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.orchestrator import (  # noqa: E402
    CaseInputError,
    CaseNotFound,
    Orchestrator,
    TransitionError,
)

FIXTURES = ROOT / "tests" / "fixtures"


def read_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.orchestrator = Orchestrator(runtime_dir=Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_flow_3_end_to_end(self):
        package = self.orchestrator.submit(read_json("request-access.json"))
        case_id = package["case_id"]
        agents = [step["agent"] for step in package["coordination"]]
        self.assertIn("inventory-agent-sim", agents)
        self.assertIn("evidence-agent-sim", agents)
        self.assertEqual(package["status"], "APPROVAL_REQUIRED")
        self.orchestrator.approve(case_id, "Ana", "DPO", "Entregar copia")
        self.orchestrator.fulfill(case_id, "Ana")
        self.orchestrator.send_response(case_id, "Ana")
        package = self.orchestrator.close(case_id, "Ana")
        self.assertEqual(package["status"], "CLOSED")
        self.assertEqual(self.orchestrator.get_case(case_id)["status"], "CLOSED")
        events = [item["event_type"] for item in self.orchestrator.evidence.entries(case_id)]
        self.assertEqual(
            events,
            [
                "CASE_SUBMITTED",
                "HITL_APPROVED",
                "FULFILLED_SIMULATED",
                "RESPONSE_SENT_SIMULATED",
                "CASE_CLOSED",
            ],
        )
        self.assertTrue(self.orchestrator.evidence.verify_chain()["valid"])

    def test_pending_identity_does_not_query_inventory(self):
        package = self.orchestrator.submit(read_json("request-identity-pending.json"))
        self.assertEqual(package["discovered_records"], [])
        self.assertIn("No consultado", package["coordination"][1]["description"])
        package = self.orchestrator.confirm_identity(
            package["case_id"], "Ana", "Presencial", "ref-1"
        )
        self.assertEqual(len(package["discovered_records"]), 2)
        stored_request = self.orchestrator.get_request(package["case_id"])
        self.assertEqual(stored_request["identity_verification"]["status"], "verified")

    def test_inventory_limits_discovery_to_registered_systems(self):
        request = read_json("request-access.json")
        request.update({"request_id": "DSAR-INV-1", "principal_id": "person-003"})
        package = self.orchestrator.submit(request)
        self.assertEqual(package["source_systems"], ["billing-demo", "crm-demo"])

    def test_duplicate_and_invalid_ids_are_rejected(self):
        self.orchestrator.submit(read_json("request-access.json"))
        with self.assertRaises(CaseInputError):
            self.orchestrator.submit(read_json("request-access.json"))
        request = read_json("request-access.json")
        request["request_id"] = "../escape"
        with self.assertRaises(CaseInputError):
            self.orchestrator.submit(request)

    def test_invalid_transition_and_unknown_case(self):
        package = self.orchestrator.submit(read_json("request-erasure.json"))
        with self.assertRaises(TransitionError):
            self.orchestrator.fulfill(package["case_id"], "Ana")
        with self.assertRaises(CaseNotFound):
            self.orchestrator.get_case("DSAR-NO-EXISTE")

    def test_generated_request_id_and_default_date(self):
        request = read_json("request-access.json")
        del request["request_id"]
        del request["received_at"]
        package = self.orchestrator.submit(request)
        self.assertTrue(package["case_id"].startswith("DSAR-"))

    def test_evidence_chain_detects_tampering(self):
        self.orchestrator.submit(read_json("request-access.json"))
        self.orchestrator.submit(read_json("request-erasure.json"))
        log = self.orchestrator.evidence.log_path
        lines = log.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        first["payload"]["status"] = "CLOSED"
        lines[0] = json.dumps(first, sort_keys=True)
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = self.orchestrator.evidence.verify_chain()
        self.assertFalse(result["valid"])

    def test_classifier_and_drafter_extension_points(self):
        orchestrator = Orchestrator(
            runtime_dir=Path(self.temp.name) / "ext",
            classifier=lambda text: "portability",
            drafter=lambda package: f"Borrador externo {package['case_id']}",
        )
        request = read_json("request-access.json")
        del request["request_type"]
        package = orchestrator.submit(request)
        self.assertEqual(package["request_type"], "portability")
        self.assertEqual(
            orchestrator.response_markdown(package["case_id"]),
            f"Borrador externo {package['case_id']}",
        )


if __name__ == "__main__":
    unittest.main()
