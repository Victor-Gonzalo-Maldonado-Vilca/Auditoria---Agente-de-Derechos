"""Server-rendered HTML pages: case inbox, request form, HITL panel, evidence."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from agents import scenarios as test_scenarios
from agents.orchestrator import AIUnavailable, CaseInputError, CaseNotFound, Orchestrator

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

RIGHT_LABELS = {
    "access": "Acceso",
    "rectification": "Rectificación",
    "erasure": "Supresión",
    "portability": "Portabilidad",
    "objection": "Oposición",
}
STATUS_LABELS = {
    "RECEIVED": "Recibida",
    "TRIAGED": "Clasificada",
    "IDENTITY_PENDING": "Identidad pendiente",
    "VERIFIED": "Verificada",
    "DISCOVERY": "Descubrimiento",
    "REVIEW": "En revisión",
    "APPROVAL_REQUIRED": "Requiere aprobación",
    "APPROVED": "Aprobada",
    "FULFILLED": "Ejecutada (simulada)",
    "CLOSED": "Cerrada",
    "REJECTED": "Rechazada",
}
STATUS_TONES = {
    "IDENTITY_PENDING": "warning",
    "REVIEW": "info",
    "APPROVAL_REQUIRED": "warning",
    "APPROVED": "success",
    "FULFILLED": "teal",
    "CLOSED": "neutral",
    "REJECTED": "danger",
}
ROLES = ["DPO", "Responsable de privacidad", "Asesoría legal"]
VERIFICATION_METHODS = ["Presencial", "Portal autenticado", "Videollamada", "Documento cotejado"]
CHANNELS = ["email-simulado", "portal-simulado", "carta-simulada"]
ACTION_ROUTES = {
    "verify-identity",
    "approve",
    "reject",
    "fulfill",
    "send",
    "close",
}
AWAITING_DECISION = {"IDENTITY_PENDING", "REVIEW", "APPROVAL_REQUIRED"}
IN_PROGRESS = {"APPROVED", "FULFILLED", "REJECTED"}
FILTERS = {
    "todos": ("Todos", lambda item: True),
    "decision": ("Esperan decisión", lambda item: item["status"] in AWAITING_DECISION),
    "curso": ("En curso", lambda item: item["status"] in IN_PROGRESS),
    "vencidos": (
        "Vencidos",
        lambda item: item["status"] != "CLOSED" and item["days_left"] < 0,
    ),
    "cerrados": ("Cerrados", lambda item: item["status"] == "CLOSED"),
}

templates.env.globals.update(
    RIGHT_LABELS=RIGHT_LABELS,
    STATUS_LABELS=STATUS_LABELS,
    STATUS_TONES=STATUS_TONES,
    ROLES=ROLES,
    VERIFICATION_METHODS=VERIFICATION_METHODS,
    CHANNELS=CHANNELS,
)
templates.env.filters["pretty_json"] = lambda value: json.dumps(
    value, indent=2, ensure_ascii=False
)
templates.env.filters["fmt_dt"] = lambda value: (
    str(value).replace("T", " ")[:16] + " UTC" if value else "—"
)
templates.env.filters["short_hash"] = lambda value: f"{str(value)[:12]}…"


def orchestrator_of(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def days_left(package: dict[str, Any]) -> int:
    return (date.fromisoformat(package["deadline_at"]) - date.today()).days


def flow_steps(package: dict[str, Any]) -> list[dict[str, str]]:
    """Etapas visibles del Flujo 3 con su estado: done, current, rejected o skipped."""
    states = {item["state"] for item in package["audit_trail"]}
    rejected = "REJECTED" in states
    steps = [
        ("Recibida", True),
        ("Identidad", "VERIFIED" in states),
        ("Datos localizados", "DISCOVERY" in states),
        (
            "Rechazada" if rejected else "Aprobada" if "APPROVED" in states else "Decisión",
            rejected or "APPROVED" in states,
        ),
        ("Ejecución", "FULFILLED" in states),
        ("Respuesta", bool(package.get("outbox"))),
        ("Cerrada", "CLOSED" in states),
    ]
    result = []
    current_found = False
    for index, (label, done) in enumerate(steps):
        if rejected and index in {1, 2, 4} and not done:
            status = "skipped"
        elif rejected and index == 3:
            status = "rejected"
        elif done:
            status = "done"
        elif not current_found:
            status = "current"
            current_found = True
        else:
            status = "todo"
        result.append({"label": label, "status": status})
    return result


def redirect(path: str, **params: str) -> RedirectResponse:
    query = urlencode({key: value for key, value in params.items() if value})
    return RedirectResponse(f"{path}?{query}" if query else path, status_code=303)


def render(request: Request, name: str, context: dict[str, Any], status_code: int = 200):
    context = {
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
        "actor": request.cookies.get("dsar_actor", ""),
        "ai": orchestrator_of(request).ai_status(),
        **context,
    }
    return templates.TemplateResponse(request, name, context, status_code=status_code)


@router.get("/", response_class=HTMLResponse)
def inbox(request: Request, filtro: str = "todos"):
    cases = orchestrator_of(request).list_cases()
    for item in cases:
        item["days_left"] = days_left(item)
    if filtro not in FILTERS:
        filtro = "todos"
    filters = [
        {
            "key": key,
            "label": label,
            "count": sum(1 for item in cases if predicate(item)),
        }
        for key, (label, predicate) in FILTERS.items()
    ]
    open_cases = [item for item in cases if item["status"] != "CLOSED"]
    return render(
        request,
        "index.html",
        {
            "cases": [item for item in cases if FILTERS[filtro][1](item)],
            "total": len(cases),
            "filters": filters,
            "active_filter": filtro,
            "pending_hitl": sum(1 for item in cases if item["status"] in AWAITING_DECISION),
            "due_soon": sum(1 for item in open_cases if 0 <= item["days_left"] <= 5),
            "overdue": sum(1 for item in open_cases if item["days_left"] < 0),
            "closed": sum(1 for item in cases if item["status"] == "CLOSED"),
        },
    )


@router.get("/solicitudes/nueva", response_class=HTMLResponse)
def new_request(request: Request):
    orchestrator = orchestrator_of(request)
    return render(
        request,
        "new_request.html",
        {
            "policies": orchestrator.policies(),
            "principals": orchestrator.inventory.known_principals() + ["person-999"],
            "today": date.today().isoformat(),
        },
    )


@router.post("/solicitudes")
async def create_request(request: Request):
    form = await request.form()
    payload = {
        "principal_id": str(form.get("principal_id", "")).strip(),
        "request_type": str(form.get("request_type", "")).strip(),
        "policy_id": str(form.get("policy_id", "")).strip(),
        "request_text": str(form.get("request_text", "")).strip(),
        "identity_verification": {
            "status": "verified" if form.get("identity_verified") == "on" else "pending",
            "method": "formulario-web",
            "reference": str(form.get("identity_reference", "")).strip() or "sin-referencia",
        },
    }
    received_at = str(form.get("received_at", "")).strip()
    if received_at:
        payload["received_at"] = received_at
    token = str(form.get("ai_suggestion_token", "")).strip()
    if token:
        payload["ai_suggestion_token"] = token
    try:
        package = orchestrator_of(request).submit(payload)
    except CaseInputError as exc:
        return redirect("/solicitudes/nueva", error=str(exc))
    return redirect(
        f"/casos/{package['case_id']}",
        msg=f"Solicitud registrada en estado {STATUS_LABELS.get(package['status'], package['status'])}.",
    )


@router.get("/casos/{case_id}", response_class=HTMLResponse)
def case_detail(request: Request, case_id: str):
    orchestrator = orchestrator_of(request)
    try:
        dsar_request, package = orchestrator.store.load(case_id)
    except CaseNotFound:
        return render(request, "error.html", {"message": f"Caso no encontrado: {case_id}"}, 404)
    return render(
        request,
        "case.html",
        {
            "case": package,
            "dsar_request": dsar_request,
            "days_left": days_left(package),
            "actions": orchestrator.available_actions(case_id),
            "draft": orchestrator.response_markdown(case_id),
            "evidence": orchestrator.evidence.entries(case_id),
            "steps": flow_steps(package),
        },
    )


@router.post("/casos/{case_id}/{action}")
async def case_action(request: Request, case_id: str, action: str):
    if action not in ACTION_ROUTES:
        return render(request, "error.html", {"message": "Accion no admitida"}, 404)
    orchestrator = orchestrator_of(request)
    form = await request.form()
    actor = str(form.get("actor", "")).strip()
    role = str(form.get("role", "")).strip()
    comment = str(form.get("comment", "")).strip()
    try:
        if action == "verify-identity":
            orchestrator.confirm_identity(
                case_id, actor, str(form.get("method", "")), str(form.get("reference", ""))
            )
            message = "Identidad confirmada y descubrimiento ejecutado."
        elif action == "approve":
            orchestrator.approve(case_id, actor, role, comment)
            message = "Plan aprobado y firmado."
        elif action == "reject":
            orchestrator.reject(case_id, actor, role, comment)
            message = "Solicitud rechazada con fundamento."
        elif action == "fulfill":
            orchestrator.fulfill(case_id, actor)
            message = "Ejecucion simulada registrada."
        elif action == "send":
            orchestrator.send_response(
                case_id, actor, str(form.get("channel", "")),
                str(form.get("draft_source", "plantilla")),
            )
            message = "Respuesta registrada en la bandeja de salida simulada."
        else:
            orchestrator.close(case_id, actor)
            message = "Caso cerrado."
    except CaseNotFound:
        return render(request, "error.html", {"message": f"Caso no encontrado: {case_id}"}, 404)
    except CaseInputError as exc:
        return redirect(f"/casos/{case_id}", error=str(exc))
    response = redirect(f"/casos/{case_id}", msg=message)
    if actor:
        response.set_cookie("dsar_actor", actor, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@router.post("/casos/{case_id}/borrador/{provider}")
async def case_ai_draft(request: Request, case_id: str, provider: str):
    form = await request.form()
    actor = str(form.get("actor", "")).strip()
    try:
        draft = orchestrator_of(request).generate_ai_draft(case_id, provider, actor)
    except CaseNotFound:
        return render(request, "error.html", {"message": f"Caso no encontrado: {case_id}"}, 404)
    except (AIUnavailable, CaseInputError) as exc:
        return redirect(f"/casos/{case_id}", error=str(exc))
    response = redirect(
        f"/casos/{case_id}",
        msg=f"Borrador generado por {draft['provider']}/{draft['model']}. Reviselo antes de elegirlo.",
    )
    response.set_cookie("dsar_actor", actor, max_age=60 * 60 * 24 * 30, samesite="lax")
    return response


@router.get("/casos/{case_id}/expediente.json")
def download_package(request: Request, case_id: str):
    package = orchestrator_of(request).get_case(case_id)
    return Response(
        json.dumps(package, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{case_id}-case-package.json"'},
    )


@router.get("/casos/{case_id}/respuesta.md")
def download_response(request: Request, case_id: str):
    body = orchestrator_of(request).response_markdown(case_id)
    return Response(
        body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{case_id}-response.md"'},
    )


@router.get("/evidencia", response_class=HTMLResponse)
def evidence(request: Request):
    orchestrator = orchestrator_of(request)
    return render(
        request,
        "evidence.html",
        {
            "entries": list(reversed(orchestrator.evidence.entries())),
            "verification": orchestrator.evidence.verify_chain(),
        },
    )


@router.get("/pruebas", response_class=HTMLResponse)
def scenarios_page(request: Request):
    catalog = test_scenarios.load_scenarios()
    results = request.app.state.scenario_results
    executed = [results[item["id"]] for item in catalog if item["id"] in results]
    return render(
        request,
        "scenarios.html",
        {
            "scenarios": catalog,
            "results": results,
            "step_labels": test_scenarios.STEP_LABELS,
            "check_labels": test_scenarios.CHECK_LABELS,
            "summary": {
                "total": len(catalog),
                "passed": sum(1 for item in executed if item["passed"]),
                "failed": sum(1 for item in executed if not item["passed"]),
                "pending": len(catalog) - len(executed),
            },
        },
    )


@router.post("/pruebas/ejecutar")
async def scenarios_run(request: Request):
    form = await request.form()
    selected = str(form.get("scenario_id", "")).strip()
    catalog = test_scenarios.load_scenarios()
    if selected:
        catalog = [item for item in catalog if item["id"] == selected]
        if not catalog:
            return redirect("/pruebas", error=f"Caso de prueba desconocido: {selected}")
    results = test_scenarios.run_all(orchestrator_of(request), catalog)
    for item in results:
        request.app.state.scenario_results[item["scenario_id"]] = item
    passed = sum(1 for item in results if item["passed"])
    message = f"{passed} de {len(results)} casos de prueba superados."
    if passed == len(results):
        return redirect("/pruebas", msg=message)
    return redirect("/pruebas", error=message + " Revise los que fallaron.")


@router.get("/inventario", response_class=HTMLResponse)
def inventory(request: Request):
    return render(
        request,
        "inventory.html",
        {"systems": orchestrator_of(request).inventory.systems()},
    )
