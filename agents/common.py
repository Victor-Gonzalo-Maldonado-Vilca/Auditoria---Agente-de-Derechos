"""Shared loading of the DSAR skill scripts and small helpers."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "dsar-rights" / "scripts"
RAG_PATH = PROJECT_ROOT / "rag" / "dsar_rag.py"
DATA_DIR = PROJECT_ROOT / "data"


def load_module(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LIFECYCLE = load_module("dsar_case_lifecycle", SCRIPTS_DIR / "case_lifecycle.py")
ENGINE = LIFECYCLE.engine
VALIDATOR = load_module("dsar_case_validator", SCRIPTS_DIR / "validate_case.py")
RAG = load_module("dsar_rag_retriever", RAG_PATH)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_rag_query(request: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in [
            str(request.get("request_type", "")),
            str(request.get("request_text", "")),
            "derechos DSAR identidad plazo revision humana",
        ]
        if part
    )
