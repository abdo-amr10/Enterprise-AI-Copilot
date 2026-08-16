"""FastAPI entrypoint for the AI runtime service.

Run with:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI

from src.api.routers import copilot_router, semantic_router

app = FastAPI(title="Enterprise AI Copilot - AI Runtime")

app.include_router(copilot_router.router)
app.include_router(semantic_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
