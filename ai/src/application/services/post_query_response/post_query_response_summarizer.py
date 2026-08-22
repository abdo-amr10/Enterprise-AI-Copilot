"""LLM-backed, best-effort summaries of Backend execution results."""

from __future__ import annotations

import json
from typing import Any, Sequence

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient


class PostQueryResponseSummarizer:
    """Produces text only; presentation and result data remain deterministic."""

    def __init__(self, llm_client: LLMClient, max_sample_rows: int = 5) -> None:
        self._llm_client = llm_client
        self._max_sample_rows = max_sample_rows

    def summarize(self, question: str, columns: Sequence[str], rows: Sequence[Sequence[Any]],
                  row_count: int, presentation_type: str) -> str:
        context = {"presentationType": presentation_type, "rowCount": row_count,
                   "columns": list(columns),
                   "sampleRows": [list(row) for row in rows[:self._max_sample_rows]]}
        prompt = (
            "You are the result summarization component of an Enterprise AI Copilot.\n"
            "Write one concise factual plain-text brief. Use only the question and result "
            "context. Do not invent facts, infer conclusions, generate SQL, or alter counts. "
            "For an Excel export, say the complete result is attached and only summarize "
            "the supplied sample.\n\n"
            f"User question: {question}\n"
            f"Result context: {json.dumps(context, default=str, ensure_ascii=False)}"
        )
        text = self._llm_client.generate(GenerationRequest(prompt=prompt)).text.strip()
        if not text:
            raise RuntimeError("The result summarizer returned empty text.")
        return text
