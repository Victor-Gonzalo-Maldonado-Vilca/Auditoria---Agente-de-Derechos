"""Orchestrator of the DSAR flow (Flujo 3 del documento PIMS multiagente).

Coordinates the Rights agent (case engine and lifecycle), the simulated
Inventory agent and the simulated Evidence agent. Every stored package is
validated before it is persisted, and every step is recorded as evidence.

Language models plug in at three points, always as proposals:
- `assistant` (Gemini/OpenRouter, `llm/dsar_llm.py`): suggests the right from
  the free text and drafts responses from minimized facts.
- `claude_agent` (Claude Code, `llm/claude_agent.py`): reads the case and the
  skill references with read-only tools and drafts a response.
- `classifier(request_text) -> request_type` and `drafter(package) -> markdown`:
  generic hooks kept for other integrations.
None of them changes the state, the identity gate or the HITL decision: every
suggestion is confirmed by a person and every draft is chosen by a person.
"""

from __future__ import annotations

import copy
import hashlib
import secrets
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from agents.common import (
    CLAUDE,
    DATA_DIR,
    ENGINE,
    LIFECYCLE,
    LLM,
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

ClaudeAgentError = CLAUDE.ClaudeAgentError
TEMPLATE_SOURCE = "plantilla"
SUGGESTION_LIMIT = 200

__all__ = [
    "AIUnavailable",
    "CaseInputError",
    "CaseNotFound",
    "Orchestrator",
    "TransitionError",
]


class AIUnavailable(CaseInputError):
    """Raised when a language model is not configured or fails to answer."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Orchestrator:
    rights_agent = "rights-agent-dsar"

    def __init__(
        self,
        data_dir: Path = DATA_DIR,
        runtime_dir: Path | None = None,
        classifier: Callable[[str], str] | None = None,
        drafter: Callable[[dict[str, Any]], str] | None = None,
        assistant: Any = None,
        claude_agent: Any = None,
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
        self.assistant = assistant
        self.claude_agent = claude_agent
        self._suggestions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, **kwargs: Any) -> "Orchestrator":
        """Orchestrator with the models configured in the environment, if any."""
        return cls(
            assistant=LLM.DsarAssistant.from_env(),
            claude_agent=CLAUDE.ClaudeCodeAgent.from_env(),
            **kwargs,
        )

    def ai_status(self) -> dict[str, Any]:
        return {
            "assistant": (
                {"provider": self.assistant.provider, "model": self.assistant.model}
                if self.assistant else None
            ),
            "claude": (
                {"provider": self.claude_agent.provider, "executable": self.claude_agent.executable}
                if self.claude_agent else None
            ),
        }

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

    # Asistencia de IA ----------------------------------------------------

    def suggest_right(self, request_text: str) -> dict[str, Any]:
        """Ask the assistant for the right; the person confirms it on submit."""
        if not self.assistant:
            raise AIUnavailable("No hay un modelo configurado (defina GEMINI_API_KEY).")
        text = request_text.strip()
        if not text:
            raise CaseInputError("Escriba el texto de la solicitud antes de pedir una sugerencia.")
        calls_before = len(self.assistant.calls)
        try:
            suggestion = self.assistant.classify_request(text)
        except LLM.LLMError as exc:
            raise AIUnavailable(f"El modelo no respondio: {exc}") from exc
        token = secrets.token_urlsafe(12)
        with self._lock:
            if len(self._suggestions) >= SUGGESTION_LIMIT:
                self._suggestions.pop(next(iter(self._suggestions)))
            self._suggestions[token] = {
                **suggestion,
                "provider": self.assistant.provider,
                "model": self.assistant.model,
                "text_sha256": sha256_text(text),
                "calls": self.assistant.calls[calls_before:],
            }
        return {
            "token": token,
            "label": LLM.RIGHT_LABELS.get(suggestion["suggested_right"] or ""),
            "provider": self.assistant.provider,
            "model": self.assistant.model,
            **suggestion,
        }

    def classification_metadata(
        self, token: str | None, request: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not token:
            return None
        with self._lock:
            suggestion = self._suggestions.pop(token, None)
        if suggestion is None:
            raise CaseInputError("La sugerencia de la IA expiro; solicitela de nuevo.")
        if suggestion["text_sha256"] != sha256_text(str(request.get("request_text", "")).strip()):
            raise CaseInputError(
                "El texto cambio despues de la sugerencia de la IA; solicitela de nuevo."
            )
        final_right = request.get("request_type")
        return {
            "enabled": True,
            "provider": suggestion["provider"],
            "model": suggestion["model"],
            "role": "Triaje asistido; la persona confirma el derecho antes de registrar.",
            "data_minimization": "Solo se envio el texto de la solicitud, sin datos del inventario.",
            "classification": {
                "suggested_right": suggestion["suggested_right"],
                "confidence": suggestion["confidence"],
                "rationale": suggestion["rationale"],
                "final_right": final_right,
                "confirmed_by_human": True,
                "accepted": suggestion["suggested_right"] == final_right,
            },
            "calls": suggestion["calls"],
            "error": None,
        }

    def generate_ai_draft(self, case_id: str, provider: str, actor: str) -> dict[str, Any]:
        """Draft a response with Gemini or Claude; the person chooses it on send."""
        actor = LIFECYCLE.require_value(actor, "actor")
        request, package = self.store.load(case_id)
        if package.get("outbox"):
            raise TransitionError("La respuesta de este caso ya fue enviada")
        if provider == "gemini":
            if not self.assistant:
                raise AIUnavailable("No hay un modelo configurado (defina GEMINI_API_KEY).")
            calls_before = len(self.assistant.calls)
            try:
                body = self.assistant.draft_response(package, str(request.get("request_text", "")))
            except LLM.LLMError as exc:
                raise AIUnavailable(f"El modelo no respondio: {exc}") from exc
            model = self.assistant
            markdown = LLM.render_ai_draft(package, body, model)
            details = {
                "data_minimization": "Hechos del expediente sin valores de PII.",
                "calls": self.assistant.calls[calls_before:],
            }
        elif provider == "claude":
            if not self.claude_agent:
                raise AIUnavailable("Claude Code no esta instalado en este equipo.")
            try:
                body = self.claude_agent.draft_response(package)
            except ClaudeAgentError as exc:
                raise AIUnavailable(str(exc)) from exc
            model = self.claude_agent
            markdown = CLAUDE.render_agent_draft(package, body, model)
            details = {
                "data_minimization": (
                    "Expediente completo con datos ficticios; herramientas de solo lectura."
                ),
                "run": dict(self.claude_agent.last_run),
            }
        else:
            raise CaseInputError(f"Proveedor de IA no admitido: {provider}")

        # The model runs outside the lock; the draft is attached to the latest state.
        with self._lock:
            request, package = self.store.load(case_id)
            if package.get("outbox"):
                raise TransitionError("La respuesta de este caso ya fue enviada")
            updated = copy.deepcopy(package)
            draft = {
                "draft_id": f"{provider}-{len(updated.get('ai_drafts', [])) + 1}",
                "provider": model.provider,
                "model": model.model,
                "generated_at": LIFECYCLE.now_iso(),
                "actor": actor,
                "status_at_generation": updated["status"],
                "body": markdown,
                "body_sha256": sha256_text(markdown),
                **details,
            }
            updated.setdefault("ai_drafts", []).append(draft)
            LIFECYCLE.append_event(
                updated, updated["status"],
                f"Borrador generado por {model.provider}/{model.model} (propuesta, no enviada).",
                actor,
            )
            self.persist(request, updated, "AI_DRAFT_GENERATED")
            return draft

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
        suggestion_token = request.pop("ai_suggestion_token", None)
        if not request.get("request_type") and self.classifier:
            request["request_type"] = self.classifier(request["request_text"])
            request["request_type_source"] = "classifier"
        try:
            check_case_id(request["request_id"])
        except ValueError as exc:
            raise CaseInputError(str(exc)) from exc
        llm = self.classification_metadata(suggestion_token, request)

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
            if llm:
                package["llm"] = llm
                coordination.insert(
                    1,
                    self.step(
                        f"{llm['provider']}/{llm['model']}",
                        f"Sugerir derecho: {llm['classification']['suggested_right']} "
                        f"(confirmado por la persona: {request['request_type']}).",
                    ),
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
        self,
        case_id: str,
        actor: str,
        channel: str = "email-simulado",
        draft_source: str = TEMPLATE_SOURCE,
    ) -> dict[str, Any]:
        with self._lock:
            request, package = self.store.load(case_id)
            if draft_source == TEMPLATE_SOURCE:
                render = self.drafter
            else:
                chosen = next(
                    (item for item in package.get("ai_drafts", [])
                     if item["draft_id"] == draft_source),
                    None,
                )
                if chosen is None:
                    raise CaseInputError(f"Borrador no encontrado: {draft_source}")
                render = lambda _package: chosen["body"]  # noqa: E731
            updated = LIFECYCLE.send_response(package, actor, channel, render)
            updated["outbox"]["source"] = draft_source
            return self.persist(request, updated, "RESPONSE_SENT_SIMULATED")

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
