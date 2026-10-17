"""Waste-Potential FastAPI application.

Routes:
  GET  /health                 — liveness check.
  POST /pathways/compare       — app.pathways.router
  POST /decision/...           — app.decision.router (prefix set by the router)
  POST /simulations            — app.platform.router: run and store a simulation
  GET  /runs                   — app.platform.router: list stored runs
  GET  /runs/{run_id}          — app.platform.router: get one stored run

Not yet mounted: core_engine (P1) routes, pending its router implementation.

Run locally with an ASGI server, e.g. ``uvicorn app.main:app`` from backend/.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import Settings, get_settings
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

    return app


app = create_app()
