from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "demo" / "dsar_simulator.py"


class SimulatorCliTests(unittest.TestCase):
    def run_scenario(self, scenario: str):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "result"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SIMULATOR),
                    "--scenario",
                    scenario,
                    "--output-dir",
                    str(output_dir),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            package = json.loads(
                (output_dir / "case-package.json").read_text(encoding="utf-8")
            )
            self.assertTrue((output_dir / "request.json").exists())
            self.assertTrue((output_dir / "response-draft.md").exists())
            return package

    def test_access_scenario(self):
        package = self.run_scenario("access")
        self.assertEqual(package["status"], "APPROVAL_REQUIRED")
        self.assertEqual(len(package["discovered_records"]), 2)
        self.assertTrue(package["rag"]["enabled"])
        self.assertGreaterEqual(len(package["rag"]["retrieved_chunks"]), 1)

    def test_pending_scenario_blocks_records(self):
        package = self.run_scenario("pending")
        self.assertEqual(package["status"], "IDENTITY_PENDING")
        self.assertEqual(package["discovered_records"], [])

    def test_erasure_scenario_does_not_execute_action(self):
        package = self.run_scenario("erasure")
        self.assertTrue(package["hitl"]["required"])
        self.assertFalse(package["proposed_action"]["executed"])


if __name__ == "__main__":
    unittest.main()
