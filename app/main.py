"""FastAPI application: REST API under /api and server-rendered HTML pages.

Run from the project root:

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agents.orchestrator import (
    AIUnavailable,
    CaseInputError,
    CaseNotFound,
    Orchestrator,
    TransitionError,
)
from app import api, web

APP_DIR = Path(__file__).resolve().parent


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    app = FastAPI(
        title="Agente de Derechos DSAR",
        description=(
            "API del prototipo academico del Agente de Derechos (ISO/IEC 27701:2025). "
            "Datos ficticios: no ejecuta cambios reales ni envia comunicaciones."
        ),
        version="0.2.0",
    )
    app.state.orchestrator = orchestrator or Orchestrator.from_env()
    app.state.scenario_results = {}

    @app.exception_handler(CaseNotFound)
    async def not_found(_: Request, exc: CaseNotFound) -> JSONResponse:
        return JSONResponse({"detail": f"Caso no encontrado: {exc.args[0]}"}, status_code=404)

    @app.exception_handler(TransitionError)
    async def invalid_transition(_: Request, exc: TransitionError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(AIUnavailable)
    async def ai_unavailable(_: Request, exc: AIUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(CaseInputError)
    async def invalid_input(_: Request, exc: CaseInputError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    app.include_router(api.router)
    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
    return app


app = create_app()
