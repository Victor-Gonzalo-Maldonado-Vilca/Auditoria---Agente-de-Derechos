from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "rag" / "dsar_rag.py"
SPEC = importlib.util.spec_from_file_location("dsar_rag", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class DsarRagTests(unittest.TestCase):
    def test_access_query_recovers_iso_control_source(self):
        result = MODULE.retrieve("acceso copia de datos PII titular", top_k=3)
        self.assertTrue(result["enabled"])
        self.assertIn("vectorial", result["method"].lower())
        self.assertEqual(result["embedding_model"], MODULE.MODEL_NAME)
        self.assertGreater(result["vector_dimensions"], 0)
        self.assertGreaterEqual(result["documents_indexed"], 3)
        self.assertTrue(result["retrieved_chunks"])
        self.assertTrue(
            any(item["source"] == "iso-control-map.md" for item in result["retrieved_chunks"])
        )

    def test_identity_query_recovers_workflow(self):
        result = MODULE.retrieve("identidad pendiente bloquear descubrimiento", top_k=2)
        self.assertTrue(
            any(
                item["source"] == "workflow-and-states.md"
                for item in result["retrieved_chunks"]
            )
        )

    def test_results_include_provenance(self):
        item = MODULE.retrieve("supresion aprobacion humana", top_k=1)["retrieved_chunks"][0]
        self.assertEqual(item["rank"], 1)
        self.assertEqual(len(item["sha256"]), 64)
        self.assertGreater(item["score"], 0)
        self.assertTrue(item["section"])

    def test_vector_store_is_persisted_and_reusable(self):
        result = MODULE.retrieve("gestion de solicitudes", top_k=1, rebuild=True)
        store = ROOT / result["vector_store"]
        self.assertTrue(store.is_file())
        self.assertEqual(len(result["vector_store_sha256"]), 64)
        index = MODULE.load_index()
        self.assertEqual(index["similarity"], "cosine")
        self.assertEqual(index["dimensions"], result["vector_dimensions"])


if __name__ == "__main__":
    unittest.main()
