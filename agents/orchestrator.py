"""Orchestrator of the DSAR flow (Flujo 3 del documento PIMS multiagente).

Coordinates the Rights agent (case engine and lifecycle), the simulated
Inventory agent and the simulated Evidence agent. Every stored package is
validated before it is persisted, and every step is recorded as evidence.

Extension points for the future LLM integration:
- `classifier(request_text) -> request_type`: used only when the request has
  no explicit `request_type`. Its output is a proposal and still passes the
  engine checks, the validator and the human approval gate.
- `drafter(package) -> markdown`: replaces the deterministic template when the
  response is drafted or sent. It never decides or executes anything.
"""

from __future__ import annotations

import copy
import secrets
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from agents.common import (
    DATA_DIR,
    ENGINE,
    LIFECYCLE,
    RAG,
    VALIDATOR,
    build_rag_query,
    json_hash,
    read_json,
)
from agents.evidence_agent import EvidenceAgent
from agents.inventory_agent import InventoryAgent
from agents.store import CaseNotFound, CaseStore, check_case_id

CaseInputError = ENGINE.CaseInputError
TransitionError = LIFECYCLE.TransitionError

__all__ = [
    "CaseInputError",
    "CaseNotFound",
    "Orchestrator",
    "TransitionError",
]


class Orchestrator:
    rights_agent = "rights-agent-dsar"

    def __init__(
        self,
        data_dir: Path = DATA_DIR,
        runtime_dir: Path | None = None,
        classifier: Callable[[str], str] | None = None,
        drafter: Callable[[dict[str, Any]], str] | None = None,
    ) -> None:
        data_dir = Path(data_dir)
        runtime_dir = Path(runtime_dir) if runtime_dir else data_dir / "runtime"
        self.policies_path = data_dir / "policies.json"
        self.inventory = InventoryAgent(
            data_dir / "inventory.json", data_dir / "pii_records.json"
        )
        self.store = CaseStore(runtime_dir / "cases")
        self.evidence = EvidenceAgent(runtime_dir / "evidence_log.jsonl")
        self.classifier = classifier
        self.drafter = drafter or ENGINE.render_response
        self._lock = threading.Lock()

    # Consultas -----------------------------------------------------------

    def policies(self) -> dict[str, Any]:
        return read_json(self.policies_path)

    def list_cases(self) -> list[dict[str, Any]]:
        return self.store.list()

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self.store.load(case_id)[1]

    def get_request(self, case_id: str) -> dict[str, Any]:
        return self.store.load(case_id)[0]

    def response_markdown(self, case_id: str) -> str:
        package = self.get_case(case_id)
        if package.get("outbox"):
            return package["outbox"]["body"]
        return self.drafter(package)

    def available_actions(self, case_id: str) -> list[str]:
        return LIFECYCLE.available_actions(self.get_case(case_id))

    # Flujo 3 -------------------------------------------------------------

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        request = copy.deepcopy(request)
        now = datetime.now()
        request.setdefault(
            "request_id", f"DSAR-{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"
        )
        request.setdefault("received_at", date.today().isoformat())
        request.setdefault("request_text", "")
        if not request.get("request_type") and self.classifier:
            request["request_type"] = self.classifier(request["request_text"])
            request["request_type_source"] = "classifier"
        try:
            check_case_id(request["request_id"])
        except ValueError as exc:
            raise CaseInputError(str(exc)) from exc

        with self._lock:
            if self.store.exists(request["request_id"]):
                raise CaseInputError(f"Ya existe el caso {request['request_id']}")
            identity = request.get("identity_verification") or {}
            verified = str(identity.get("status", "")).lower() == "verified"
            coordination = [self.step(self.rights_agent, "Registrar y clasificar")]
            if verified:
                located = self.inventory.locate(str(request.get("principal_id", "")))
                records = located["records"]
                coordination.append(
                    self.step(
                        self.inventory.name,
                        f"Localizar PII en {len(located['systems_consulted'])} sistemas "
                        f"inventariados: {len(records)} registros.",
                    )
                )
            else:
                records = []
                coordination.append(
                    self.step(self.inventory.name, "No consultado: identidad no verificada.")
                )
            source_hashes = {
                "request": json_hash(request),
                "data": self.inventory.records_sha256(),
                "policies": ENGINE.sha256_file(self.policies_path),
            }
            rag_context = RAG.retrieve(build_rag_query(request), top_k=3)
            package = ENGINE.build_case(
                request, records, self.policies(), source_hashes, rag_context=rag_context
            )
            coordination.append(
                self.step(self.rights_agent, f"Expediente preparado en estado {package['status']}.")
            )
            coordination.append(
                self.step(self.evidence.name, "Registrar solicitud y expediente.")
            )
            package["coordination"] = coordination
            self.persist(request, package, "CASE_SUBMITTED")
            return package

    # Ciclo de vida con aprobacion humana -----------------------------------

    def confirm_identity(
        self, case_id: str, actor: str, method: str, reference: str
    ) -> dict[str, Any]:
        with self._lock:
            request, package = self.store.load(case_id)
            located = self.inventory.locate(package["principal_id"])
            updated = LIFECYCLE.confirm_identity(
                package, request, located["records"], self.policies(),
                actor, method, reference,
            )
            updated.setdefault("coordination", []).append(
                self.step(
                    self.inventory.name,
                    f"Localizar PII tras verificar identidad: "
                    f"{len(located['records'])} registros.",
                )
            )
            request = copy.deepcopy(request)
            request["identity_verification"] = updated["identity_verification"]
            return self.persist(request, updated, "IDENTITY_VERIFIED")

    def approve(self, case_id: str, approver: str, role: str, comment: str) -> dict[str, Any]:
        return self.transition(case_id, "HITL_APPROVED", LIFECYCLE.approve, approver, role, comment)

    def reject(self, case_id: str, approver: str, role: str, reason: str) -> dict[str, Any]:
        return self.transition(case_id, "HITL_REJECTED", LIFECYCLE.reject, approver, role, reason)

    def fulfill(self, case_id: str, actor: str) -> dict[str, Any]:
        return self.transition(case_id, "FULFILLED_SIMULATED", LIFECYCLE.fulfill, actor)

    def send_response(
        self, case_id: str, actor: str, channel: str = "email-simulado"
    ) -> dict[str, Any]:
        return self.transition(
            case_id, "RESPONSE_SENT_SIMULATED", LIFECYCLE.send_response,
            actor, channel, self.drafter,
        )

    def close(self, case_id: str, actor: str) -> dict[str, Any]:
        return self.transition(case_id, "CASE_CLOSED", LIFECYCLE.close, actor)

    # Internos ------------------------------------------------------------

    def transition(self, case_id: str, event_type: str, action, *args) -> dict[str, Any]:
        with self._lock:
            request, package = self.store.load(case_id)
            updated = action(package, *args)
            return self.persist(request, updated, event_type)

    def persist(
        self, request: dict[str, Any], package: dict[str, Any], event_type: str
    ) -> dict[str, Any]:
        errors = VALIDATOR.validate(package)
        if errors:
            raise CaseInputError("Expediente invalido: " + "; ".join(errors))
        self.store.save(request, package)
        self.evidence.record(
            package["case_id"],
            event_type,
            {
                "status": package["status"],
                "audit_events": len(package["audit_trail"]),
                "package_sha256": json_hash(package),
            },
            LIFECYCLE.now_iso(),
        )
        return package

    @staticmethod
    def step(agent: str, description: str) -> dict[str, Any]:
        return {"agent": agent, "description": description, "at": LIFECYCLE.now_iso()}
