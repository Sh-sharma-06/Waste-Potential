"""Main FastAPI application for Waste-Potential."""

from app.platform.assistant.router import router as assistant_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core_engine.router import router as science_router
from app.decision.router import router as decision_router
from app.pathways.router import router as pathways_router

app = FastAPI(
    title="Waste-Potential API",
    description="Waste treatment simulation, decision support, and AI assistance.",
    version="1.0.0",
)

# Local frontend development only. Restrict origins further for deployment.
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

# Preserve the existing scientific and decision-making implementations.
app.include_router(science_router, prefix="/api/v1")
app.include_router(decision_router, prefix="/api/v1")
app.include_router(pathways_router, prefix="/api/v1")
app.include_router(assistant_router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "waste-potential-api"}


@app.get("/api/v1/health", tags=["Health"])
def api_health_check():
    return {"status": "ok", "service": "waste-potential-api"}