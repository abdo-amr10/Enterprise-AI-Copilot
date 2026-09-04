"""Follow-up Analyzer (spec section 5).

Classifies the current question against recent candidate turns. Only sees
lightweight metadata about each recent turn (turn_id, its question text,
and whether SQL/a result summary exist for it) -- never the SQL or result
content itself. That's intentional: classification only needs to know
*what kind* of context might be needed, not the content of it. The actual
content is pulled afterwards, only for the fields the classification
calls for (see ContextRetriever), per the "retrieve only what's required"
principle.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from src.application.dto.conversation.conversation_llm_schemas import FollowupAnalysisResult
from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.application.services.conversation.enums import ContextRequirement, FollowupClassification
from src.application.services.conversation.models import ConversationTurn
from src.prompts.followup_analysis_prompt import FOLLOWUP_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)


class FollowupAnalyzer:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def analyze(
        self, current_question: str, recent_turns: tuple[ConversationTurn, ...]
    ) -> FollowupAnalysisResult:
        if not recent_turns:
            return FollowupAnalysisResult(
                classification=FollowupClassification.INDEPENDENT.value,
                confidence=1.0,
                context_requirement=ContextRequirement.NONE.value,
                referenced_turn_id=None,
            )

        prompt = FOLLOWUP_ANALYSIS_PROMPT.format(
            recent_turns=self._render_turns(recent_turns),
            current_question=current_question,
        )

        try:
            response = self._llm_client.generate(
                GenerationRequest(prompt=prompt, response_model=FollowupAnalysisResult)
            )
            return FollowupAnalysisResult.model_validate_json(response.text)
        except (ValidationError, Exception) as exc:  # noqa: BLE001 - deliberate fail-safe
            logger.warning("Follow-up analysis failed, defaulting to AMBIGUOUS: %s", exc)
            # Fail-safe: never guess a classification we can't trust. Per
            # spec section 10, an unresolved reference must ask for
            # clarification rather than silently proceeding.
            return FollowupAnalysisResult(
                classification=FollowupClassification.AMBIGUOUS.value,
                confidence=0.0,
                context_requirement=ContextRequirement.NONE.value,
                referenced_turn_id=None,
            )

    @staticmethod
    def _render_turns(turns: tuple[ConversationTurn, ...]) -> str:
        lines = []
        for turn in turns:
            has_sql = "yes" if turn.generated_sql else "no"
            has_result = "yes" if turn.execution_result_summary else "no"
            lines.append(
                f"- turn_id={turn.turn_id} | question=\"{turn.user_question}\" "
                f"| has_sql={has_sql} | has_result={has_result}"
            )
        return "\n".join(lines)
