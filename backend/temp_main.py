from fastapi import FastAPI
from app.decision.router import router as decision_router
from app.pathways.router import router as pathways_router

app = FastAPI(title="P4 Standalone Testing API")

app.include_router(decision_router, prefix="/decision")
app.include_router(pathways_router)

@app.get("/")
def health_check():
    return {"status": "P4 module is running"}