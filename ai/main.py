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

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.dependencies import get_schema_provider, get_semantic_repository
from src.api.routers import copilot_router, debug_router, semantic_router

logger = logging.getLogger("ai_runtime.semantic_watcher")
_POLL_INTERVAL_SECONDS = float(os.getenv("SEMANTIC_SYNC_INTERVAL_SECONDS", "60"))


async def _semantic_index_watcher(interval_seconds: float = _POLL_INTERVAL_SECONDS) -> None:
    """Periodically check Backend status and update in-memory index and schema when active revision changes."""
    loop = asyncio.get_running_loop()
    while True:
        try:
            repo = get_semantic_repository()
            if hasattr(repo, "sync_active_index"):
                updated = await loop.run_in_executor(None, repo.sync_active_index)
                if updated:
                    logger.info("Semantic in-memory index synchronized with revision: %s", repo.indexed_revision_id)
            schema_provider = get_schema_provider()
            if hasattr(schema_provider, "sync_schema"):
                await loop.run_in_executor(None, schema_provider.sync_schema)
        except asyncio.CancelledError:
            break
        except Exception as err:
            logger.debug("Semantic index watcher check skipped: %s", err)

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    watcher_task = asyncio.create_task(_semantic_index_watcher())

    # Pre-warm LLM model in background to eliminate cold-load delay on the first query
    loop = asyncio.get_running_loop()

    def _warmup_llm() -> None:
        try:
            from src.infrastructure.llm.model_config import QWEN_CONFIG
            from src.infrastructure.llm.ollama_client import OllamaClient
            client = OllamaClient(QWEN_CONFIG)
            client.warmup()
            logger.info("Ollama model '%s' pre-warmed into memory.", QWEN_CONFIG.model_name)
        except Exception as err:
            logger.debug("Ollama warmup skipped: %s", err)

    loop.run_in_executor(None, _warmup_llm)

    yield
    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Enterprise AI Copilot - AI Runtime", lifespan=lifespan)

app.include_router(copilot_router.router)
app.include_router(semantic_router.router)
app.include_router(debug_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

