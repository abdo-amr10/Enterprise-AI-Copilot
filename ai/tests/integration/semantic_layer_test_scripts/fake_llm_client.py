"""A deterministic stand-in for LLMClient used by the integration test.

Instead of guessing intent from the prompt text, each scenario hands
this a queue of canned JSON strings, one per expected LLM call, in the
exact order the pipelines will call `.generate()`. This keeps the test
fully deterministic and makes it obvious, when a test fails, exactly
which step in the pipeline consumed which canned response.
"""

from __future__ import annotations

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse


class FakeLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._queue: list[str] = list(responses)
        self.calls: list[str] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.calls.append(request.prompt)

        if not self._queue:
            raise AssertionError(
                "FakeLLMClient ran out of canned responses -- the "
                "pipeline made more LLM calls than the scenario "
                "expected. Prompt was:\n" + request.prompt[:500]
            )

        text = self._queue.pop(0)

        return GenerationResponse(text=text)
