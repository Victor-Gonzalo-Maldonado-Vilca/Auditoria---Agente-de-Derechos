#!/usr/bin/env python3
"""Validate invariants of a generated DSAR demonstration package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_STATES = {
    "RECEIVED",
    "TRIAGED",
    "IDENTITY_PENDING",
    "VERIFIED",
    "DISCOVERY",
    "REVIEW",
    "APPROVAL_REQUIRED",
    "APPROVED",
    "FULFILLED",
    "CLOSED",
    "ON_HOLD",
    "REJECTED",
    "PARTIALLY_FULFILLED",
    "ESCALATED",
    "CANCELLED",
}


def validate(package: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "case_id",
        "request_type",
        "status",
        "deadline_at",
        "identity_verification",
        "discovered_records",
        "hitl",
        "proposed_action",
        "audit_trail",
        "source_hashes",
        "rag",
        "disclaimer",
    }
    missing = required - package.keys()
    if missing:
        errors.append(f"Campos faltantes: {sorted(missing)}")
        return errors
    if package["status"] not in ALLOWED_STATES:
        errors.append("Estado no admitido")
    if package["proposed_action"].get("executed") is not False:
        errors.append("El prototipo no puede declarar una accion ejecutada")
    identity_status = package["identity_verification"].get("status")
    if identity_status != "verified" and package["discovered_records"]:
        errors.append("Se descubrieron datos sin identidad verificada")
    if package["request_type"] in {"rectification", "erasure", "objection"}:
        if not package["hitl"].get("required"):
            errors.append("Una accion de mutacion o restriccion requiere HITL")
    sequences = [item.get("sequence") for item in package["audit_trail"]]
    if sequences != list(range(1, len(sequences) + 1)):
        errors.append("La secuencia de auditoria no es continua")
    for record in package["discovered_records"]:
        if not record.get("record_id") or not record.get("source_system"):
            errors.append("Registro sin procedencia completa")
        for field in record.get("redacted_fields", []):
            if field in record.get("data", {}):
                errors.append(f"Campo de tercero no redactado: {field}")
    if set(package["source_hashes"]) != {"request", "data", "policies"}:
        errors.append("Faltan hashes de las entradas")
    rag = package.get("rag", {})
    if rag.get("enabled"):
        required_metadata = {
            "method", "embedding_model", "query", "vector_store",
            "vector_store_sha256", "vector_dimensions"
        }
        if required_metadata - rag.keys():
            errors.append("Metadatos RAG incompletos")
        if rag.get("vector_dimensions", 0) <= 0:
            errors.append("Dimension vectorial RAG invalida")
        if len(str(rag.get("vector_store_sha256", ""))) != 64:
            errors.append("Almacen vectorial sin huella SHA-256 valida")
        for item in rag.get("retrieved_chunks", []):
            required_rag = {
                "rank", "score", "chunk_id", "source", "section", "sha256", "excerpt"
            }
            if required_rag - item.keys():
                errors.append("Fragmento RAG sin procedencia completa")
            if len(str(item.get("sha256", ""))) != 64:
                errors.append("Fragmento RAG sin huella SHA-256 valida")
    llm = package.get("llm", {})
    if llm.get("enabled"):
        if not llm.get("provider") or not llm.get("model"):
            errors.append("Asistente IA sin proveedor o modelo registrado")
        for call in llm.get("calls", []):
            if len(str(call.get("prompt_sha256", ""))) != 64 or len(
                str(call.get("response_sha256", ""))
            ) != 64:
                errors.append("Llamada al modelo sin huellas SHA-256 validas")
        classification = llm.get("classification")
        if classification and classification.get("confirmed_by_human") is not True:
            errors.append("La clasificacion de la IA no fue confirmada por un humano")
        if classification and classification.get("final_right") != package["request_type"]:
            errors.append("El derecho final no coincide con la confirmacion humana")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    package = json.loads(args.package.read_text(encoding="utf-8"))
    errors = validate(package)
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        return 1
    print("VALID: expediente DSAR consistente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
