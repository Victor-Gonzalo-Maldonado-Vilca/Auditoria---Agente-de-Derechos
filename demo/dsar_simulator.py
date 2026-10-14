#!/usr/bin/env python3
"""Interactive and scripted simulator for the academic DSAR skill."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
ENGINE_PATH = PROJECT_ROOT / "skills" / "dsar-rights" / "scripts" / "dsar_case.py"
VALIDATOR_PATH = PROJECT_ROOT / "skills" / "dsar-rights" / "scripts" / "validate_case.py"
RAG_PATH = PROJECT_ROOT / "rag" / "dsar_rag.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ENGINE = load_module("dsar_case_engine", ENGINE_PATH)
VALIDATOR = load_module("dsar_case_validator", VALIDATOR_PATH)
RAG = load_module("dsar_rag_retriever", RAG_PATH)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def choose(prompt: str, options: list[tuple[str, str]]) -> str:
    while True:
        print(f"\n{prompt}")
        for key, label in options:
            print(f"  {key}. {label}")
        selected = input("Seleccione una opcion: ").strip()
        values = {key for key, _ in options}
        if selected in values:
            return selected
        print("Opcion no valida. Intente nuevamente.")


def ask_yes_no(prompt: str) -> bool:
    while True:
        value = input(f"{prompt} [s/n]: ").strip().lower()
        if value in {"s", "si", "sí"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Responda s o n.")


def build_interactive_request() -> dict[str, Any]:
    print("\n=== SIMULADOR ACADEMICO DEL AGENTE DSAR ===")
    print("Use solamente los datos ficticios incluidos en el proyecto.")

    right_key = choose(
        "Derecho que se desea simular:",
        [
            ("1", "Acceso"),
            ("2", "Rectificacion"),
            ("3", "Supresion"),
            ("4", "Portabilidad"),
            ("5", "Oposicion"),
        ],
    )
    right = {
        "1": "access",
        "2": "rectification",
        "3": "erasure",
        "4": "portability",
        "5": "objection",
    }[right_key]
    principal_key = choose(
        "Titular ficticio:",
        [
            ("1", "person-001 (incluye datos sensibles y de terceros)"),
            ("2", "person-002 (caso simple)"),
            ("3", "person-999 (sin registros)"),
        ],
    )
    principal_id = {"1": "person-001", "2": "person-002", "3": "person-999"}[
        principal_key
    ]
    verified = ask_yes_no("¿La identidad fue verificada por el canal autorizado?")
    policy_key = choose(
        "Politica ficticia para el calculo del plazo:",
        [
            ("1", "LAB-30: 30 dias"),
            ("2", "LAB-15-REVIEW: 15 dias y revision especializada"),
        ],
    )
    policy_id = {"1": "LAB-30", "2": "LAB-15-REVIEW"}[policy_key]
    request_text = input(
        "Descripcion breve de la solicitud (opcional): "
    ).strip() or "Solicitud generada mediante el simulador academico."
    now = datetime.now()
    return {
        "request_id": f"DSAR-SIM-{now:%Y%m%d-%H%M%S}",
        "principal_id": principal_id,
        "request_type": right,
        "received_at": date.today().isoformat(),
        "policy_id": policy_id,
        "request_text": request_text,
        "identity_verification": {
            "status": "verified" if verified else "pending",
            "method": "simulador-local",
            "reference": f"sim-verification-{now:%Y%m%d%H%M%S}",
        },
    }


def load_scenario(name: str) -> dict[str, Any]:
    scenario_files = {
        "access": "request-access.json",
        "pending": "request-identity-pending.json",
        "erasure": "request-erasure.json",
    }
    return read_json(FIXTURES / scenario_files[name])


def print_summary(package: dict[str, Any], output_dir: Path) -> None:
    print("\n=== RESULTADO DE LA SIMULACION ===")
    print(f"Caso:              {package['case_id']}")
    print(f"Derecho:           {package['request_type']}")
    print(f"Estado:            {package['status']}")
    print(f"Fecha limite:      {package['deadline_at']}")
    print(f"Registros:         {len(package['discovered_records'])}")
    print(f"Revision humana:   {'SI' if package['hitl']['required'] else 'NO'}")
    print(f"Fuentes RAG:       {len(package['rag']['retrieved_chunks'])}")
    if package["hitl"]["reasons"]:
        print("Motivos:")
        for reason in package["hitl"]["reasons"]:
            print(f"  - {reason}")
    print("\nArchivos generados:")
    print(f"  - {output_dir / 'request.json'}")
    print(f"  - {output_dir / 'case-package.json'}")
    print(f"  - {output_dir / 'response-draft.md'}")
    print("\nLa respuesta es un borrador. Ninguna accion fue ejecutada.")


def run(request: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    records_path = FIXTURES / "subject-data.json"
    policies_path = FIXTURES / "policies.json"
    records = read_json(records_path)
    policies = read_json(policies_path)
    source_hashes = {
        "request": json_hash(request),
        "data": ENGINE.sha256_file(records_path),
        "policies": ENGINE.sha256_file(policies_path),
    }
    rag_query = " ".join(
        part
        for part in [
            str(request.get("request_type", "")),
            str(request.get("request_text", "")),
            "derechos DSAR identidad plazo revision humana",
        ]
        if part
    )
    rag_context = RAG.retrieve(rag_query, top_k=3)
    package = ENGINE.build_case(
        request, records, policies, source_hashes, rag_context=rag_context
    )
    errors = VALIDATOR.validate(package)
    if errors:
        raise RuntimeError("Expediente invalido: " + "; ".join(errors))

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "request.json").write_text(
        json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "case-package.json").write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "response-draft.md").write_text(
        ENGINE.render_response(package), encoding="utf-8"
    )
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=["interactive", "access", "pending", "erasure"],
        default="interactive",
        help="Modo interactivo o escenario preparado.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directorio de salida. Por defecto usa simulaciones/<case-id>.",
    )
    args = parser.parse_args()

    request = (
        build_interactive_request()
        if args.scenario == "interactive"
        else load_scenario(args.scenario)
    )
    output_dir = args.output_dir or (
        PROJECT_ROOT / "simulaciones" / request["request_id"].lower()
    )
    try:
        package = run(request, output_dir.resolve())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print_summary(package, output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
