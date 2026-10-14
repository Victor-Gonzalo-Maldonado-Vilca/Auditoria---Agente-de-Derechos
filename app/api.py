"""REST API over the orchestrator. Documented automatically at /docs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from agents import scenarios as test_scenarios
from agents.orchestrator import Orchestrator

router = APIRouter(prefix="/api", tags=["DSAR"])

RightType = Literal["access", "rectification", "erasure", "portability", "objection"]


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


class IdentityIn(BaseModel):
    status: Literal["verified", "pending"] = "pending"
    method: str = "portal-demo"
    reference: str = ""


class RequestIn(BaseModel):
    request_id: str | None = Field(None, description="Se genera si se omite.")
    principal_id: str
    request_type: RightType | None = Field(
        None, description="Obligatorio mientras no exista un clasificador configurado."
    )
    received_at: str | None = Field(None, description="YYYY-MM-DD; por defecto hoy.")
    policy_id: str
    request_text: str = ""
    identity_verification: IdentityIn = IdentityIn()
    ai_suggestion_token: str | None = Field(
        None, description="Token de /api/assist/classify si la IA sugirio el derecho."
    )


class SuggestIn(BaseModel):
    request_text: str


class DraftIn(BaseModel):
    provider: Literal["gemini", "claude"]
    actor: str


class IdentityConfirmationIn(BaseModel):
    actor: str
    method: str
    reference: str


class DecisionIn(BaseModel):
    approver: str
    role: str
    comment: str


class ActorIn(BaseModel):
    actor: str


class SendIn(ActorIn):
    channel: str = "email-simulado"
    draft_source: str = Field(
        "plantilla", description="'plantilla' o el draft_id de un borrador de IA."
    )


def summary(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": package["case_id"],
        "principal_id": package["principal_id"],
        "request_type": package["request_type"],
        "status": package["status"],
        "received_at": package["received_at"],
        "deadline_at": package["deadline_at"],
        "hitl_required": package["hitl"]["required"],
    }


def with_actions(orchestrator: Orchestrator, package: dict[str, Any]) -> dict[str, Any]:
    return {
        **package,
        "available_actions": orchestrator.available_actions(package["case_id"]),
    }


@router.get("/assist/status")
def assist_status(orchestrator: Orchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    return orchestrator.ai_status()


@router.post("/assist/classify")
def assist_classify(
    payload: SuggestIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    """Sugerencia de la IA; la persona confirma el derecho al registrar la solicitud."""
    return orchestrator.suggest_right(payload.request_text)


@router.post("/cases/{case_id}/drafts", status_code=201)
def create_draft(
    case_id: str, payload: DraftIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    """Genera un borrador con Gemini o Claude. No cambia el estado del caso."""
    return orchestrator.generate_ai_draft(case_id, payload.provider, payload.actor)


@router.get("/scenarios", tags=["Casos de prueba"])
def list_scenarios() -> list[dict[str, Any]]:
    return test_scenarios.load_scenarios()


@router.post("/scenarios/run", tags=["Casos de prueba"])
def run_scenarios(
    scenario_id: str | None = None, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    """Ejecuta todos los casos de prueba (o uno, con `scenario_id`) y compara lo esperado."""
    catalog = test_scenarios.load_scenarios()
    if scenario_id:
        catalog = [item for item in catalog if item["id"] == scenario_id]
    results = test_scenarios.run_all(orchestrator, catalog) if catalog else []
    return {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "results": results,
    }


@router.get("/policies")
def policies(orchestrator: Orchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    return orchestrator.policies()


@router.get("/inventory")
def inventory(orchestrator: Orchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    return {
        "systems": orchestrator.inventory.systems(),
        "known_principals": orchestrator.inventory.known_principals(),
    }


@router.post("/requests", status_code=201)
def create_request(
    payload: RequestIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    package = orchestrator.submit(payload.model_dump(exclude_none=True))
    return with_actions(orchestrator, package)


@router.get("/cases")
def list_cases(orchestrator: Orchestrator = Depends(get_orchestrator)) -> list[dict[str, Any]]:
    return [summary(item) for item in orchestrator.list_cases()]


@router.get("/cases/{case_id}")
def get_case(case_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    return with_actions(orchestrator, orchestrator.get_case(case_id))


@router.get("/cases/{case_id}/response.md", response_class=PlainTextResponse)
def get_response(case_id: str, orchestrator: Orchestrator = Depends(get_orchestrator)) -> str:
    return orchestrator.response_markdown(case_id)


@router.post("/cases/{case_id}/verify-identity")
def verify_identity(
    case_id: str,
    payload: IdentityConfirmationIn,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    package = orchestrator.confirm_identity(
        case_id, payload.actor, payload.method, payload.reference
    )
    return with_actions(orchestrator, package)


@router.post("/cases/{case_id}/approve")
def approve(
    case_id: str, payload: DecisionIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    package = orchestrator.approve(case_id, payload.approver, payload.role, payload.comment)
    return with_actions(orchestrator, package)


@router.post("/cases/{case_id}/reject")
def reject(
    case_id: str, payload: DecisionIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    package = orchestrator.reject(case_id, payload.approver, payload.role, payload.comment)
    return with_actions(orchestrator, package)


@router.post("/cases/{case_id}/fulfill")
def fulfill(
    case_id: str, payload: ActorIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    return with_actions(orchestrator, orchestrator.fulfill(case_id, payload.actor))


@router.post("/cases/{case_id}/send")
def send(
    case_id: str, payload: SendIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    package = orchestrator.send_response(
        case_id, payload.actor, payload.channel, payload.draft_source
    )
    return with_actions(orchestrator, package)


@router.post("/cases/{case_id}/close")
def close(
    case_id: str, payload: ActorIn, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> dict[str, Any]:
    return with_actions(orchestrator, orchestrator.close(case_id, payload.actor))


@router.get("/evidence")
def evidence(
    case_id: str | None = None, orchestrator: Orchestrator = Depends(get_orchestrator)
) -> list[dict[str, Any]]:
    return orchestrator.evidence.entries(case_id)


@router.get("/evidence/verify")
def verify_evidence(orchestrator: Orchestrator = Depends(get_orchestrator)) -> dict[str, Any]:
    return orchestrator.evidence.verify_chain()
