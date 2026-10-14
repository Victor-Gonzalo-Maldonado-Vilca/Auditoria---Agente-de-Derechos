#!/usr/bin/env python3
"""Build a deterministic, non-production DSAR case package from synthetic JSON."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


RIGHTS = {"access", "rectification", "erasure", "portability", "objection"}
MUTATING_RIGHTS = {"rectification", "erasure", "objection"}
DISCLAIMER = (
    "Demostracion academica con datos sinteticos. No ejecuta cambios, no envia "
    "comunicaciones y no constituye asesoramiento legal."
)


class CaseInputError(ValueError):
    """Raised when an input cannot safely produce a case package."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CaseInputError(f"Campo obligatorio invalido: {field}")
    return value.strip()


def parse_received_at(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CaseInputError("received_at debe usar YYYY-MM-DD") from exc


def event(sequence: int, state: str, description: str) -> dict[str, Any]:
    return {"sequence": sequence, "state": state, "description": description}


def redact_third_party_fields(record: dict[str, Any]) -> dict[str, Any]:
    prepared = {
        "record_id": require_text(record, "record_id"),
        "source_system": require_text(record, "source_system"),
        "category": require_text(record, "category"),
        "sensitive": bool(record.get("sensitive", False)),
        "data": copy.deepcopy(record.get("data", {})),
        "redacted_fields": [],
        "restrictions": list(record.get("restrictions", [])),
    }
    if not isinstance(prepared["data"], dict):
        raise CaseInputError(f"data debe ser un objeto en {prepared['record_id']}")
    for field in record.get("third_party_fields", []):
        if field in prepared["data"]:
            prepared["data"].pop(field)
            prepared["redacted_fields"].append(field)
    return prepared


def proposed_action(request_type: str) -> dict[str, Any]:
    descriptions = {
        "access": "Preparar una copia revisada de la PII localizada.",
        "portability": "Preparar una exportacion estructurada y legible por maquina.",
        "rectification": "Proponer correcciones; no actualizar sistemas sin aprobacion y evidencia.",
        "erasure": "Proponer supresion o desidentificacion tras revisar retencion y excepciones.",
        "objection": "Proponer restriccion o cese de la finalidad objetada tras revision.",
    }
    return {
        "type": request_type,
        "description": descriptions[request_type],
        "executed": False,
    }


def build_case(
    request: dict[str, Any],
    records: list[dict[str, Any]],
    policies: dict[str, Any],
    source_hashes: dict[str, str] | None = None,
    rag_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_id = require_text(request, "request_id")
    principal_id = require_text(request, "principal_id")
    request_type = require_text(request, "request_type").lower()
    policy_id = require_text(request, "policy_id")
    received_at = parse_received_at(require_text(request, "received_at"))

    if request_type not in RIGHTS:
        raise CaseInputError(f"request_type no admitido: {request_type}")
    policy = policies.get(policy_id)
    if not isinstance(policy, dict):
        raise CaseInputError(f"Politica desconocida: {policy_id}")
    response_days = policy.get("response_days")
    if not isinstance(response_days, int) or response_days <= 0:
        raise CaseInputError("response_days debe ser un entero positivo")

    identity = request.get("identity_verification")
    if not isinstance(identity, dict):
        raise CaseInputError("Falta identity_verification")
    identity_status = require_text(identity, "status").lower()
    identity_summary = {
        "status": identity_status,
        "method": identity.get("method"),
        "reference": identity.get("reference"),
    }

    deadline = received_at + timedelta(days=response_days)
    trail = [
        event(1, "RECEIVED", "Solicitud registrada."),
        event(2, "TRIAGED", "Derecho y politica clasificados."),
    ]
    package: dict[str, Any] = {
        "case_id": request_id,
        "principal_id": principal_id,
        "request_type": request_type,
        "received_at": received_at.isoformat(),
        "policy": {
            "policy_id": policy_id,
            "label": policy.get("label", policy_id),
            "response_days": response_days,
            "disclaimer": policy.get("disclaimer", "Politica sin nota explicativa."),
        },
        "deadline_at": deadline.isoformat(),
        "identity_verification": identity_summary,
        "status": "TRIAGED",
        "discovered_records": [],
        "source_systems": [],
        "hitl": {"required": False, "reasons": []},
        "proposed_action": proposed_action(request_type),
        "audit_trail": trail,
        "source_hashes": source_hashes or {},
        "rag": rag_context
        or {
            "enabled": False,
            "method": "No configurado",
            "query": "",
            "documents_indexed": 0,
            "chunks_indexed": 0,
            "retrieved_chunks": [],
        },
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "disclaimer": DISCLAIMER,
    }

    if identity_status != "verified":
        package["status"] = "IDENTITY_PENDING"
        package["hitl"] = {
            "required": True,
            "reasons": ["La identidad no ha sido verificada por un mecanismo autorizado."],
        }
        trail.append(
            event(3, "IDENTITY_PENDING", "Descubrimiento bloqueado hasta verificar identidad.")
        )
        return package

    trail.append(event(3, "VERIFIED", "Verificacion externa confirmada."))
    matched = []
    for record in records:
        if record.get("principal_id") == principal_id:
            matched.append(redact_third_party_fields(record))
    package["discovered_records"] = matched
    package["source_systems"] = sorted({item["source_system"] for item in matched})
    trail.append(
        event(4, "DISCOVERY", f"Se localizaron {len(matched)} registros sinteticos.")
    )

    reasons: list[str] = []
    if request_type in MUTATING_RIGHTS:
        reasons.append("El derecho solicitado puede modificar o restringir el tratamiento.")
    if any(item["sensitive"] for item in matched):
        reasons.append("El expediente contiene categorias marcadas como sensibles.")
    if any(item["redacted_fields"] for item in matched):
        reasons.append("Se detectaron campos de terceros que requieren revision.")
    if any(item["restrictions"] for item in matched):
        reasons.append("Existen restricciones o conflictos de retencion pendientes de evaluar.")
    if bool(policy.get("legal_review_required", False)):
        reasons.append("La politica configurada exige revision especializada.")

    if reasons:
        package["status"] = "APPROVAL_REQUIRED"
        package["hitl"] = {"required": True, "reasons": reasons}
        trail.append(event(5, "APPROVAL_REQUIRED", "El caso requiere decision humana."))
    else:
        package["status"] = "REVIEW"
        trail.append(event(5, "REVIEW", "Borrador preparado para revision humana."))
    return package


def render_decision(package: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    approvals = package.get("approvals", [])
    if approvals:
        lines.extend(["", "## Decision humana", ""])
        labels = {"approve": "Aprobado", "reject": "Rechazado"}
        for item in approvals:
            lines.append(
                f"- {labels.get(item['decision'], item['decision'])} por "
                f"{item['approver']} ({item['role']}) el {item['decided_at']}: "
                f"{item['comment']}"
            )
    execution = package.get("execution")
    if execution:
        lines.extend(["", "## Ejecucion (simulada)", ""])
        lines.append(f"- {execution['summary']}")
        for record in execution["affected_records"]:
            lines.append(f"  - `{record}`")
    return lines


def render_response(package: dict[str, Any]) -> str:
    title = "Respuesta DSAR" if package.get("approvals") else "Borrador de respuesta DSAR"
    lines = [
        f"# {title}",
        "",
        f"**Caso:** {package['case_id']}  ",
        f"**Derecho solicitado:** {package['request_type']}  ",
        f"**Estado:** {package['status']}  ",
        f"**Fecha limite configurada:** {package['deadline_at']}",
        "",
        "## Resultado preliminar",
        "",
    ]
    if package["identity_verification"]["status"] != "verified":
        lines.append(
            "La busqueda de datos no se inicio porque la verificacion de identidad esta pendiente."
        )
    else:
        lines.append(
            f"Se prepararon {len(package['discovered_records'])} registros sinteticos "
            f"procedentes de {len(package['source_systems'])} sistemas."
        )
        lines.extend(["", "## Informacion preparada", ""])
        if not package["discovered_records"]:
            lines.append("No se localizaron registros para el identificador proporcionado.")
        for record in package["discovered_records"]:
            lines.append(
                f"- `{record['source_system']}/{record['record_id']}` "
                f"({record['category']}): `{json.dumps(record['data'], ensure_ascii=False)}`"
            )
            if record["redacted_fields"]:
                lines.append(
                    "  - Campos de terceros retirados del borrador: "
                    + ", ".join(record["redacted_fields"])
                )
    lines.extend(render_decision(package))
    pending_title = (
        "Revisiones consideradas" if package.get("approvals") else "Acciones o revisiones pendientes"
    )
    lines.extend(["", f"## {pending_title}", ""])
    lines.append(f"- {package['proposed_action']['description']}")
    for reason in package["hitl"]["reasons"]:
        lines.append(f"- Revision humana: {reason}")
    retrieved = package.get("rag", {}).get("retrieved_chunks", [])
    if retrieved:
        lines.extend(["", "## Fundamento recuperado por el RAG", ""])
        for item in retrieved:
            lines.append(
                f"- [{item['chunk_id']}] `{item['source']}` — {item['section']} "
                f"(relevancia {item['score']})."
            )
    lines.extend(["", "---", "", package["disclaimer"]])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--policies", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    request = load_json(args.request)
    records = load_json(args.data)
    policies = load_json(args.policies)
    if not isinstance(request, dict) or not isinstance(records, list) or not isinstance(policies, dict):
        raise CaseInputError("Tipos JSON de entrada invalidos")

    hashes = {
        "request": sha256_file(args.request),
        "data": sha256_file(args.data),
        "policies": sha256_file(args.policies),
    }
    package = build_case(request, records, policies, hashes)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    package_path = args.output_dir / "case-package.json"
    response_path = args.output_dir / "response-draft.md"
    package_path.write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    response_path.write_text(render_response(package), encoding="utf-8")
    print(package_path)
    print(response_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
