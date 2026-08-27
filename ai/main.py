from pathlib import Path
import os

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.is_file():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from fastapi import FastAPI

from src.api.routers import copilot_router, debug_router, semantic_router

app = FastAPI(title="Enterprise AI Copilot - AI Runtime")

app.include_router(copilot_router.router)
app.include_router(semantic_router.router)
app.include_router(debug_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

