"""LLM-backed, best-effort summaries of Backend execution results."""

from __future__ import annotations

import json
from typing import Any, Sequence

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.prompts.post_query_response_summary_prompt import (
    POST_QUERY_RESPONSE_SUMMARY_PROMPT,
)


class PostQueryResponseSummarizer:
    """Produces text only; presentation and result data remain deterministic."""

    def __init__(self, llm_client: LLMClient, max_sample_rows: int = 5) -> None:
        self._llm_client = llm_client
        self._max_sample_rows = max_sample_rows

    def summarize(self, question: str, columns: Sequence[str], rows: Sequence[Sequence[Any]],
                  row_count: int, presentation_type: str) -> str:
        context = {"presentationType": presentation_type, "row_count": row_count,
                   "columns": list(columns), "sample_rows": [list(row) for row in rows[:self._max_sample_rows]],
                   "available_statistics": self._statistics(columns, rows)}
        prompt = POST_QUERY_RESPONSE_SUMMARY_PROMPT.format(
            question=question, context=json.dumps(context, default=str, ensure_ascii=False)
        )
        text = self._llm_client.generate(GenerationRequest(prompt=prompt)).text.strip()
        if not text:
            raise RuntimeError("The result summarizer returned empty text.")
        return text

    @staticmethod
    def _statistics(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> dict[str, Any]:
        """Return only deterministic statistics calculated from the supplied result."""
        result: dict[str, Any] = {"non_null_counts": {}}
        for index, column in enumerate(columns):
            values = [row[index] for row in rows if len(row) > index and row[index] is not None]
            result["non_null_counts"][column] = len(values)
            numeric = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
            if numeric:
                result.setdefault("numeric", {})[column] = {
                    "min": min(numeric), "max": max(numeric), "sum": sum(numeric), "average": sum(numeric) / len(numeric)
                }
        return result
