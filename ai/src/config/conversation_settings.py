"""Runtime configuration for the Conversation Layer.

Configuration is intentionally kept outside application business logic,
matching the existing SelfCorrectionSettings / SemanticSettings pattern.
"""
import os
from dataclasses import dataclass
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ConversationSettings:
    # Number of most-recent turns considered as CANDIDATE context for the
    # current question.
    context_window: int = 5
    semantic_router_enabled: bool = os.getenv("CONVERSATION_SEMANTIC_ROUTER_ENABLED", "true").lower() in ("true", "1", "yes")
    semantic_model_path: Path = Path(os.getenv(
        "CONVERSATION_EMBEDDING_MODEL_PATH",
        str(AI_ROOT / "models" / "embeddings" / "all-MiniLM-L6-v2"),
    ))
    min_similarity: float = float(os.getenv("CONVERSATION_SEMANTIC_MIN_SIMILARITY", "0.35"))
    min_margin: float = float(os.getenv("CONVERSATION_SEMANTIC_MIN_MARGIN", "0.025"))
    device: str | None = os.getenv("CONVERSATION_EMBEDDING_DEVICE", None)
    llm_fallback_enabled: bool = os.getenv("CONVERSATION_LLM_FALLBACK_ENABLED", "true").lower() in ("true", "1", "yes")


CONVERSATION_SETTINGS = ConversationSettings()

