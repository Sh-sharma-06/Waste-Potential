
"""Waste-Potential FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.api.external import router as external_router
from app.api.geocode import router as geocode_router
from app.core_engine.router import router as core_engine_router
from app.data.buyers import router as buyers_router
from app.decision.router import router as decision_router
from app.errors import register_error_handlers
from app.ml.router import router as ml_router
from app.ml.vision_router import router as vision_router
from app.pathways.explain_router import router as explain_router
from app.recyclables.recyclables_router import router as recyclables_router
from app.pathways.router import router as pathways_router
from app.platform.assistant.router import router as assistant_router
from app.platform.router import router as platform_router
from app.schemas.common import BaseSchema


class HealthResponse(BaseSchema):
    status: str
    environment: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name)

    register_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["Platform"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            environment=settings.environment,
        )

    # Preserve the existing platform and scientific-engine routers.
    app.include_router(pathways_router)
    app.include_router(explain_router)
    app.include_router(decision_router)
    app.include_router(platform_router)
    app.include_router(core_engine_router)

    # Keep the Gemini assistant under its existing API prefix.
    app.include_router(assistant_router, prefix="/api/v1")

    # P3 external-data endpoints: /weather and /facilities.
    app.include_router(external_router)

    # Geocoding: /geocode
    app.include_router(geocode_router)

    # P4 buyer discovery: /buyers
    app.include_router(buyers_router)

    # Vision classification and advice: /vision/classify, /vision/advice
    app.include_router(vision_router)

    # Recyclables: /recyclables/buyers, /recyclables/prices
    app.include_router(recyclables_router)

    # ML yield model: /ml/yield, /ml/models
    app.include_router(ml_router)
    
    return app


app = create_app()
