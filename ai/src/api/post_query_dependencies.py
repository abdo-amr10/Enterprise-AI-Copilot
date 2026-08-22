"""Composition root for post-execution result formatting."""

from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.config.post_query_response_settings import PostQueryResponseSettings


_formatter: PostQueryResponseFormatter | None = None


def get_post_query_response_formatter() -> PostQueryResponseFormatter:
    global _formatter
    if _formatter is None:
        _formatter = PostQueryResponseFormatter(PostQueryResponseSettings())
    return _formatter
