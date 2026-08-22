"""Composition root for post-execution result formatting."""

from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.config.post_query_response_settings import PostQueryResponseSettings
from src.application.services.post_query_response.post_query_response_summarizer import PostQueryResponseSummarizer
from src.infrastructure.llm.model_config import QWEN_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient


_formatter: PostQueryResponseFormatter | None = None


def get_post_query_response_formatter() -> PostQueryResponseFormatter:
    global _formatter
    if _formatter is None:
        _formatter = PostQueryResponseFormatter(
            PostQueryResponseSettings(),
            summarizer=PostQueryResponseSummarizer(OllamaClient(config=QWEN_CONFIG)),
        )
    return _formatter
