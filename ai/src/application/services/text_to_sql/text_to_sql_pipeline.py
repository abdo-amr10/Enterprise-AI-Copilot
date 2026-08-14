"""Application pipeline for query-time Text-to-SQL generation."""

from datetime import date

from ai.src.application.dto.llm.generation_request import GenerationRequest
from ai.src.application.dto.llm.generation_response import GenerationResponse
from ai.src.prompts.text_to_sql_prompt import TEXT_TO_SQL_PROMPT
from ai.src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.application.services.text_to_sql.sql_generation_service import (
    SQLGenerationService,
)


class TextToSQLPipeline:
    """
    Orchestrates semantic-context retrieval and SQL generation.
    """

    def __init__(
        self,
        context_retrieval_service: ContextRetrievalService,
        sql_generation_service: SQLGenerationService,
    ) -> None:
        self._context_retrieval_service = context_retrieval_service
        self._sql_generation_service = sql_generation_service

    def run(
        self,
        question: str,
        top_k: int | None = None,
    ) -> GenerationResponse:
        semantic_context = (
            self._context_retrieval_service.build_llm_context(
                question=question,
                top_k=top_k,
            )
        )

        prompt = TEXT_TO_SQL_PROMPT.format(
            semantic_context=semantic_context,
            question=question,
            current_date=date.today().isoformat(),
        )

        request = GenerationRequest(
            prompt=prompt,
        )

        return self._sql_generation_service.generate(request)