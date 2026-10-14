from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "dsar-rights" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LIFECYCLE = load("dsar_case_lifecycle", SCRIPTS / "case_lifecycle.py")
VALIDATOR = load("dsar_case_validator", SCRIPTS / "validate_case.py")
ENGINE = LIFECYCLE.engine


def read_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CaseLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = read_json("subject-data.json")
        cls.policies = read_json("policies.json")

    def build(self, name: str):
        hashes = {"request": "0" * 64, "data": "0" * 64, "policies": "0" * 64}
        return ENGINE.build_case(read_json(name), self.records, self.policies, hashes)

    def assertValid(self, package):
        self.assertEqual(VALIDATOR.validate(package), [])

    def test_access_case_full_lifecycle_until_closed(self):
        package = self.build("request-access.json")
        package = LIFECYCLE.approve(package, "Ana", "DPO", "Entregar copia revisada")
        self.assertEqual(package["status"], "APPROVED")
        package = LIFECYCLE.fulfill(package, "Ana")
        package = LIFECYCLE.send_response(package, "Ana")
        package = LIFECYCLE.close(package, "Ana")
        self.assertEqual(package["status"], "CLOSED")
        self.assertEqual(package["outbox"]["sent"], "simulated")
        self.assertIn("## Decision humana", package["outbox"]["body"])
        sequences = [item["sequence"] for item in package["audit_trail"]]
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))
        self.assertValid(package)

    def test_erasure_execution_is_simulated_and_only_after_approval(self):
        package = self.build("request-erasure.json")
        with self.assertRaises(LIFECYCLE.TransitionError):
            LIFECYCLE.fulfill(package, "Ana")
        package = LIFECYCLE.approve(package, "Ana", "DPO", "Revisada la retencion")
        package = LIFECYCLE.fulfill(package, "Ana")
        self.assertTrue(package["proposed_action"]["executed"])
        self.assertTrue(package["proposed_action"]["simulated"])
        self.assertEqual(len(package["execution"]["affected_records"]), 2)
        self.assertValid(package)

    def test_rejection_can_be_sent_and_closed_without_execution(self):
        package = self.build("request-identity-pending.json")
        package = LIFECYCLE.reject(package, "Ana", "DPO", "Identidad no acreditada")
        package = LIFECYCLE.send_response(package, "Ana")
        package = LIFECYCLE.close(package, "Ana")
        self.assertEqual(package["status"], "CLOSED")
        self.assertFalse(package["proposed_action"]["executed"])
        self.assertValid(package)

    def test_cannot_approve_while_identity_is_pending(self):
        package = self.build("request-identity-pending.json")
        with self.assertRaises(LIFECYCLE.TransitionError):
            LIFECYCLE.approve(package, "Ana", "DPO", "ok")

    def test_decision_requires_comment(self):
        package = self.build("request-access.json")
        with self.assertRaises(LIFECYCLE.CaseInputError):
            LIFECYCLE.approve(package, "Ana", "DPO", "  ")

    def test_confirm_identity_runs_discovery(self):
        request = read_json("request-identity-pending.json")
        package = self.build("request-identity-pending.json")
        package = LIFECYCLE.confirm_identity(
            package, request, self.records, self.policies, "Ana", "Presencial", "ref-1"
        )
        self.assertEqual(package["status"], "APPROVAL_REQUIRED")
        self.assertEqual(len(package["discovered_records"]), 2)
        self.assertEqual(package["identity_verification"]["status"], "verified")
        self.assertValid(package)

    def test_cannot_close_before_sending(self):
        package = self.build("request-access.json")
        package = LIFECYCLE.approve(package, "Ana", "DPO", "ok")
        package = LIFECYCLE.fulfill(package, "Ana")
        with self.assertRaises(LIFECYCLE.TransitionError):
            LIFECYCLE.close(package, "Ana")

    def test_validator_detects_tampered_decision(self):
        package = self.build("request-access.json")
        package = LIFECYCLE.approve(package, "Ana", "DPO", "ok")
        package["approvals"][0]["approver"] = "Otra persona"
        self.assertIn(
            "La huella de una decision humana no coincide", VALIDATOR.validate(package)
        )

    def test_validator_rejects_execution_without_approval(self):
        package = self.build("request-erasure.json")
        package["proposed_action"]["executed"] = True
        self.assertIn(
            "Una accion solo puede ejecutarse tras aprobacion humana",
            VALIDATOR.validate(package),
        )

    def test_available_actions_follow_state(self):
        pending = self.build("request-identity-pending.json")
        self.assertEqual(LIFECYCLE.available_actions(pending), ["verify_identity", "reject"])
        approved = LIFECYCLE.approve(self.build("request-access.json"), "Ana", "DPO", "ok")
        self.assertEqual(LIFECYCLE.available_actions(approved), ["fulfill"])


if __name__ == "__main__":
    unittest.main()
