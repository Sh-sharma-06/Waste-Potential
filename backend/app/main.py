"""Waste-Potential FastAPI application.

Routes:
  GET  /health                 — liveness check.
  POST /pathways/compare       — app.pathways.router
  POST /decision/...           — app.decision.router (prefix set by the router)
  POST /simulations            — app.platform.router: run and store a simulation
  GET  /runs                   — app.platform.router: list stored runs
  GET  /runs/{run_id}          — app.platform.router: get one stored run
  GET  /parameters             — app.core_engine.router: parameter registry
  POST /simulations/{run_id}/uncertainty
                               — app.core_engine.router: Monte Carlo on a stored run
  GET  /validation/summary     — app.core_engine.router: validation summary

Run locally with an ASGI server, e.g. ``uvicorn app.main:app`` from backend/.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.core_engine.router import router as core_engine_router
from app.decision.router import router as decision_router
from app.errors import register_error_handlers
from app.pathways.router import router as pathways_router
from app.platform.router import router as platform_router
from app.schemas.common import BaseSchema


class HealthResponse(BaseSchema):
    status: str
    environment: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name)

    register_error_handlers(app)

    @app.get("/health", response_model=HealthResponse, tags=["Platform"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", environment=settings.environment)

    # Each router declares its own prefix; do not add another here.
    app.include_router(pathways_router)
    app.include_router(decision_router)
    app.include_router(platform_router)
    # P1 routes; reads runs from the platform store via app.platform.runs.get_run.
    app.include_router(core_engine_router)

    return app


app = create_app()
