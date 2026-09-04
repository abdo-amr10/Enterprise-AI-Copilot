"""Fake LLM client that returns pre-canned JSON responses in sequence.

Used to unit-test FollowupAnalyzer / ContextResolver / ResultResolver /
ConversationLayer without a live Ollama server.
"""

from __future__ import annotations

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse


class FakeSequentialLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.prompts.append(request.prompt)
        if not self._responses:
            raise RuntimeError("FakeSequentialLLMClient ran out of canned responses.")
        return GenerationResponse(text=self._responses.pop(0))


class FailingLLMClient:
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise RuntimeError("LLM unavailable")
