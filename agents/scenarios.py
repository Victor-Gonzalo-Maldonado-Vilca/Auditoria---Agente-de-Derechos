"""Test scenarios for the DSAR flow, runnable from the web and the test suite.

Each scenario registers a fictitious request through the orchestrator, applies
lifecycle steps as a test operator and compares the resulting package with the
expected values. Scenarios never use language models: they check the
deterministic controls (identity gate, redaction, HITL, simulated execution
and evidence).
"""

from __future__ import annotations

import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Any

from agents.common import DATA_DIR, LIFECYCLE, VALIDATOR, read_json

SCENARIOS_PATH = DATA_DIR / "test_scenarios.json"
TEST_ACTOR = "Equipo de pruebas"
TEST_ROLE = "DPO"
STEP_LABELS = {
    "verify_identity": "Confirmar identidad",
    "approve": "Aprobar",
    "reject": "Rechazar",
    "fulfill": "Ejecutar (simulado)",
    "send": "Enviar respuesta",
    "close": "Cerrar",
}
CHECK_LABELS = {
    "status": "Estado final",
    "records": "Registros localizados",
    "redacted_fields": "Campos de terceros retirados",
    "hitl_required": "Requiere revision humana",
    "hitl_reason_contains": "Motivo de revision humana",
    "executed": "Accion ejecutada",
    "identity": "Identidad",
    "deadline_days": "Dias de plazo",
    "approvals": "Decisiones humanas",
    "response_sent": "Respuesta registrada",
    "error_contains": "Operacion bloqueada",
}


def load_scenarios(path: Path = SCENARIOS_PATH) -> list[dict[str, Any]]:
    return read_json(path)["scenarios"]


def build_request(scenario: dict[str, Any]) -> dict[str, Any]:
    spec = scenario["request"]
    now = datetime.now()
    return {
        "request_id": f"PRUEBA-{scenario['id']}-{now:%H%M%S}-{secrets.token_hex(2).upper()}",
        "principal_id": spec["principal_id"],
        "request_type": spec["request_type"],
        "policy_id": spec["policy_id"],
        "received_at": date.today().isoformat(),
        "request_text": spec["request_text"],
        "identity_verification": {
            "status": spec["identity"],
            "method": "caso-de-prueba",
            "reference": f"prueba-{scenario['id'].lower()}",
        },
    }


def apply_step(orchestrator, case_id: str, step: str) -> None:
    if step == "verify_identity":
        orchestrator.confirm_identity(case_id, TEST_ACTOR, "Portal autenticado", "verif-prueba")
    elif step == "approve":
        orchestrator.approve(case_id, TEST_ACTOR, TEST_ROLE, "Aprobado en el caso de prueba.")
    elif step == "reject":
        orchestrator.reject(
            case_id, TEST_ACTOR, TEST_ROLE,
            "Rechazado: obligacion de conservacion ficticia documentada.",
        )
    elif step == "fulfill":
        orchestrator.fulfill(case_id, TEST_ACTOR)
    elif step == "send":
        orchestrator.send_response(case_id, TEST_ACTOR)
    elif step == "close":
        orchestrator.close(case_id, TEST_ACTOR)
    else:
        raise ValueError(f"Paso desconocido: {step}")


def observe(package: dict[str, Any], key: str, error: str | None) -> Any:
    if key == "status":
        return package["status"]
    if key == "records":
        return len(package["discovered_records"])
    if key == "redacted_fields":
        return sorted({f for item in package["discovered_records"] for f in item["redacted_fields"]})
    if key == "hitl_required":
        return package["hitl"]["required"]
    if key == "hitl_reason_contains":
        return package["hitl"]["reasons"]
    if key == "executed":
        return package["proposed_action"]["executed"]
    if key == "identity":
        return package["identity_verification"]["status"]
    if key == "deadline_days":
        return (date.fromisoformat(package["deadline_at"]) - date.fromisoformat(package["received_at"])).days
    if key == "approvals":
        return [item["decision"] for item in package.get("approvals", [])]
    if key == "response_sent":
        return bool(package.get("outbox"))
    if key == "error_contains":
        return error
    raise ValueError(f"Comprobacion desconocida: {key}")


def matches(key: str, expected: Any, actual: Any) -> bool:
    if key == "hitl_reason_contains":
        return any(str(expected).lower() in reason.lower() for reason in actual)
    if key == "error_contains":
        return actual is not None and str(expected).lower() in actual.lower()
    if key == "redacted_fields":
        return sorted(expected) == actual
    return expected == actual


def check(label: str, expected: Any, actual: Any, ok: bool) -> dict[str, Any]:
    return {"label": label, "expected": expected, "actual": actual, "ok": ok}


def run_scenario(orchestrator, scenario: dict[str, Any]) -> dict[str, Any]:
    """Run one scenario and return each check with its expected and actual value."""
    result: dict[str, Any] = {
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "ran_at": LIFECYCLE.now_iso(),
        "case_id": None,
        "error": None,
        "checks": [],
    }
    try:
        package = orchestrator.submit(build_request(scenario))
    except Exception as exc:  # noqa: BLE001 - a failed scenario is reported, not raised
        result["error"] = f"No se pudo registrar la solicitud: {exc}"
        result["passed"] = False
        return result
    case_id = package["case_id"]
    result["case_id"] = case_id

    step_error = None
    for step in scenario.get("steps", []):
        try:
            apply_step(orchestrator, case_id, step)
        except LIFECYCLE.CaseInputError as exc:
            step_error = f"{STEP_LABELS.get(step, step)}: {exc}"
            break
    package = orchestrator.get_case(case_id)

    expected = scenario["expected"]
    for key, value in expected.items():
        actual = observe(package, key, step_error)
        result["checks"].append(check(CHECK_LABELS.get(key, key), value, actual, matches(key, value, actual)))
    if step_error and "error_contains" not in expected:
        result["checks"].append(check("Pasos del ciclo sin errores", None, step_error, False))

    errors = VALIDATOR.validate(package)
    result["checks"].append(check("Validador del expediente", [], errors, not errors))
    chain = orchestrator.evidence.verify_chain()
    result["checks"].append(
        check("Cadena de evidencia integra", True, chain.get("valid"), bool(chain.get("valid")))
    )
    result["passed"] = all(item["ok"] for item in result["checks"])
    return result


def run_all(orchestrator, scenarios: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    return [run_scenario(orchestrator, item) for item in (scenarios or load_scenarios())]
