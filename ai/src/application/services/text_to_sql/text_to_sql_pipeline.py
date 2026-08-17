"""Application pipeline for query-time Text-to-SQL generation."""

from src.application.dto.llm.generation_response import GenerationResponse
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.application.services.text_to_sql.sql_generation_service import (
    SQLGenerationService,
)
from src.application.services.text_to_sql.prompt_service import PromptService
from datetime import date


class TextToSQLPipeline:
    """
    Orchestrates semantic-context retrieval and SQL generation.
    """

    def __init__(
        self,
        context_retrieval_service: ContextRetrievalService,
        sql_generation_service: SQLGenerationService,
        prompt_service: PromptService | None = None,
    ) -> None:
        self._context_retrieval_service = context_retrieval_service
        self._sql_generation_service = sql_generation_service
        self._prompt_service = prompt_service or PromptService()

    def build_context(self, question: str, top_k: int | None = None) -> str:
        return self._context_retrieval_service.build_llm_context(question=question, top_k=top_k)

    def run(
        self,
        question: str,
        top_k: int | None = None,
        semantic_context: str | None = None,
    ) -> GenerationResponse:
        context = semantic_context if semantic_context is not None else self.build_context(question, top_k)
        request = self._prompt_service.build_request(question, context, date.today().isoformat())

        return self._sql_generation_service.generate(request)
