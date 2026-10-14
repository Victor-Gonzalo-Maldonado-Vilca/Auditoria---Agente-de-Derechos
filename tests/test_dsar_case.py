from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "dsar-rights" / "scripts" / "dsar_case.py"
FIXTURES = ROOT / "tests" / "fixtures"
SPEC = importlib.util.spec_from_file_location("dsar_case", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def read_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class DsarCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = read_json("subject-data.json")
        cls.policies = read_json("policies.json")

    def test_access_case_redacts_third_party_and_requires_review(self):
        package = MODULE.build_case(
            read_json("request-access.json"), self.records, self.policies
        )
        self.assertEqual(package["status"], "APPROVAL_REQUIRED")
        self.assertEqual(len(package["discovered_records"]), 2)
        crm = next(
            item for item in package["discovered_records"] if item["record_id"] == "crm-001"
        )
        self.assertNotIn("manager_email", crm["data"])
        self.assertIn("manager_email", crm["redacted_fields"])
        self.assertFalse(package["proposed_action"]["executed"])

    def test_unverified_identity_blocks_discovery(self):
        package = MODULE.build_case(
            read_json("request-identity-pending.json"), self.records, self.policies
        )
        self.assertEqual(package["status"], "IDENTITY_PENDING")
        self.assertEqual(package["discovered_records"], [])
        self.assertTrue(package["hitl"]["required"])

    def test_erasure_is_only_a_proposal(self):
        package = MODULE.build_case(
            read_json("request-erasure.json"), self.records, self.policies
        )
        self.assertEqual(package["status"], "APPROVAL_REQUIRED")
        self.assertFalse(package["proposed_action"]["executed"])
        self.assertTrue(
            any("modificar" in reason for reason in package["hitl"]["reasons"])
        )

    def test_unknown_policy_is_rejected(self):
        request = read_json("request-access.json")
        request["policy_id"] = "UNKNOWN"
        with self.assertRaises(MODULE.CaseInputError):
            MODULE.build_case(request, self.records, self.policies)


if __name__ == "__main__":
    unittest.main()
