from src.application.dto.llm.generation_request import GenerationRequest
from src.prompts.text_to_sql_prompt import TEXT_TO_SQL_PROMPT


class PromptService:
    """Builds generation requests for Text-to-SQL operations.

    The service combines a validated user question with prepared
    semantic context and the predefined Text-to-SQL instructions.

    It does not perform semantic retrieval, LLM invocation, SQL
    generation, or SQL validation.
    """

    def build_request(
        self,
        question: str,
        semantic_context: str,
        current_date: str,
        correction_feedback: str = "",
    ) -> GenerationRequest:
        """Build a generation request from question and semantic context.

        Args:
            question: A validated natural-language user question.
            semantic_context: Relevant semantic information prepared
                for the current question.
            current_date=current_date:Reference date used to interpret relative date
            expressions such as "today", "this month", or "last 30 days".

        Returns:
            A GenerationRequest containing the final Text-to-SQL prompt.

        Raises:
            ValueError: If the semantic context is empty.
        """
        if not semantic_context.strip():
            raise ValueError("semantic_context cannot be empty.")

        prompt = TEXT_TO_SQL_PROMPT.format(
            question=question,
            semantic_context=semantic_context,
            current_date=current_date,
            correction_feedback=correction_feedback,
        )

        return GenerationRequest(prompt=prompt)
