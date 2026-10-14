#!/usr/bin/env python3
"""Human-in-the-loop lifecycle transitions for a DSAR demonstration package.

Every function receives a case package, returns an updated copy and appends a
sequential audit event with actor and timestamp. Execution and delivery are
always simulated: no source system is modified and no message leaves the
prototype.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsar_case as engine  # noqa: E402


CaseInputError = engine.CaseInputError


class TransitionError(CaseInputError):
    """Raised when an action is not allowed from the current case state."""


APPROVABLE_STATES = {"REVIEW", "APPROVAL_REQUIRED"}
REJECTABLE_STATES = {"IDENTITY_PENDING", "REVIEW", "APPROVAL_REQUIRED"}
SENDABLE_STATES = {"FULFILLED", "REJECTED"}

EXECUTION_SUMMARIES = {
    "access": "Copia revisada de {count} registros preparada para entrega al titular.",
    "portability": "Exportacion JSON estructurada de {count} registros preparada.",
    "rectification": (
        "Rectificacion registrada como simulada; los sistemas origen no se modificaron."
    ),
    "erasure": (
        "Supresion simulada: {count} registros marcados para supresion o "
        "desidentificacion; los sistemas origen no se modificaron."
    ),
    "objection": (
        "Restriccion simulada del tratamiento objetado sobre {count} registros; "
        "los sistemas origen no se modificaron."
    ),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_state(package: dict[str, Any], allowed: set[str], action: str) -> None:
    if package.get("status") not in allowed:
        raise TransitionError(
            f"No se puede {action} un caso en estado {package.get('status')}; "
            f"estados admitidos: {', '.join(sorted(allowed))}"
        )


def require_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaseInputError(f"Campo obligatorio invalido: {field}")
    return value.strip()


def append_event(
    package: dict[str, Any], state: str, description: str, actor: str
) -> None:
    trail = package["audit_trail"]
    item = engine.event(len(trail) + 1, state, description)
    item["actor"] = actor
    item["timestamp"] = now_iso()
    trail.append(item)
    package["status"] = state


def record_decision(
    package: dict[str, Any], decision: str, approver: str, role: str, comment: str
) -> dict[str, Any]:
    entry = {
        "decision": decision,
        "approver": require_value(approver, "approver"),
        "role": require_value(role, "role"),
        "comment": require_value(comment, "comment"),
        "decided_at": now_iso(),
        "case_id": package["case_id"],
        "status_before": package["status"],
        "hitl_reasons": list(package["hitl"]["reasons"]),
    }
    entry["decision_sha256"] = canonical_sha256(entry)
    package.setdefault("approvals", []).append(entry)
    return entry


def confirm_identity(
    package: dict[str, Any],
    request: dict[str, Any],
    records: list[dict[str, Any]],
    policies: dict[str, Any],
    actor: str,
    method: str,
    reference: str,
) -> dict[str, Any]:
    require_state(package, {"IDENTITY_PENDING"}, "confirmar la identidad de")
    actor = require_value(actor, "actor")
    verified_request = copy.deepcopy(request)
    verified_request["identity_verification"] = {
        "status": "verified",
        "method": require_value(method, "method"),
        "reference": require_value(reference, "reference"),
    }
    rebuilt = engine.build_case(
        verified_request, records, policies, package["source_hashes"], package["rag"]
    )
    updated = copy.deepcopy(package)
    for key in ("identity_verification", "discovered_records", "source_systems", "hitl"):
        updated[key] = rebuilt[key]
    # Reutiliza los eventos VERIFIED, DISCOVERY y el estado final del motor.
    for item in rebuilt["audit_trail"][2:]:
        append_event(updated, item["state"], item["description"], actor)
    return updated


def approve(
    package: dict[str, Any], approver: str, role: str, comment: str
) -> dict[str, Any]:
    require_state(package, APPROVABLE_STATES, "aprobar")
    updated = copy.deepcopy(package)
    entry = record_decision(updated, "approve", approver, role, comment)
    append_event(
        updated, "APPROVED", f"Plan aprobado por {entry['approver']} ({entry['role']}).",
        entry["approver"],
    )
    return updated


def reject(
    package: dict[str, Any], approver: str, role: str, reason: str
) -> dict[str, Any]:
    require_state(package, REJECTABLE_STATES, "rechazar")
    updated = copy.deepcopy(package)
    entry = record_decision(updated, "reject", approver, role, reason)
    append_event(
        updated, "REJECTED",
        f"Solicitud rechazada por {entry['approver']} ({entry['role']}) con fundamento documentado.",
        entry["approver"],
    )
    return updated


def fulfill(package: dict[str, Any], actor: str) -> dict[str, Any]:
    require_state(package, {"APPROVED"}, "ejecutar")
    actor = require_value(actor, "actor")
    updated = copy.deepcopy(package)
    records = updated["discovered_records"]
    request_type = updated["request_type"]
    execution = {
        "simulated": True,
        "executed_at": now_iso(),
        "actor": actor,
        "summary": EXECUTION_SUMMARIES[request_type].format(count=len(records)),
        "affected_records": [
            f"{item['source_system']}/{item['record_id']}" for item in records
        ],
    }
    if request_type == "portability":
        execution["export"] = [
            {"record_id": item["record_id"], "category": item["category"], "data": item["data"]}
            for item in records
        ]
    updated["execution"] = execution
    updated["proposed_action"]["executed"] = True
    updated["proposed_action"]["simulated"] = True
    append_event(updated, "FULFILLED", f"Ejecucion simulada: {execution['summary']}", actor)
    return updated


def send_response(
    package: dict[str, Any],
    actor: str,
    channel: str = "email-simulado",
    render: Callable[[dict[str, Any]], str] = engine.render_response,
) -> dict[str, Any]:
    require_state(package, SENDABLE_STATES, "enviar la respuesta de")
    if package.get("outbox"):
        raise TransitionError("La respuesta de este caso ya fue enviada")
    actor = require_value(actor, "actor")
    updated = copy.deepcopy(package)
    body = render(updated)
    updated["outbox"] = {
        "channel": require_value(channel, "channel"),
        "sent": "simulated",
        "sent_at": now_iso(),
        "actor": actor,
        "body": body,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    append_event(
        updated, updated["status"],
        f"Respuesta registrada en la bandeja de salida simulada ({updated['outbox']['channel']}).",
        actor,
    )
    return updated


def close(package: dict[str, Any], actor: str) -> dict[str, Any]:
    require_state(package, SENDABLE_STATES, "cerrar")
    if not package.get("outbox"):
        raise TransitionError("No se puede cerrar un caso sin respuesta enviada")
    actor = require_value(actor, "actor")
    updated = copy.deepcopy(package)
    append_event(updated, "CLOSED", "Caso comunicado y cerrado.", actor)
    return updated


def available_actions(package: dict[str, Any]) -> list[str]:
    status = package.get("status")
    actions = []
    if status == "IDENTITY_PENDING":
        actions.append("verify_identity")
    if status in APPROVABLE_STATES:
        actions.append("approve")
    if status in REJECTABLE_STATES:
        actions.append("reject")
    if status == "APPROVED":
        actions.append("fulfill")
    if status in SENDABLE_STATES and not package.get("outbox"):
        actions.append("send")
    if status in SENDABLE_STATES and package.get("outbox"):
        actions.append("close")
    return actions
