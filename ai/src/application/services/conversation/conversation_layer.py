"""Conversation Layer -- top-level orchestrator (spec sections 1-16).

Single entry point: ``ConversationLayer.process(question, raw_conversation)``.
Wires together ConversationManager -> FollowupAnalyzer -> ContextRetriever
-> ContextResolver / ResultResolver, and returns the structured decision
contract from section 16.

This class contains NO SQL generation logic (kept separate per section 4)
and never calls the existing NL2SQL pipeline itself -- the caller
(CopilotRuntimePipeline) decides what to do with ``next_action``.
"""

from __future__ import annotations

from typing import Any

from src.application.dto.conversation.conversation_decision import ConversationDecision
from src.application.services.conversation.context_resolver import ContextResolver
from src.application.services.conversation.context_retriever import ContextRetriever
from src.application.services.conversation.conversation_manager import ConversationManager
from src.application.services.conversation.enums import (
    REQUIREMENT_FIELDS,
    ContextRequirement,
    FollowupClassification,
    NextAction,
)
from src.application.services.conversation.followup_analyzer import FollowupAnalyzer
from src.application.services.conversation.result_resolver import ResultResolver

_OUT_OF_SCOPE_MESSAGE = (
    "I can only help with questions about your data -- new queries, "
    "follow-ups on a previous query, or questions about a previous result."
)
_CLARIFICATION_MESSAGE = (
    "I'm not sure what that's referring to. Could you clarify which "
    "previous question or result you mean?"
)


class ConversationLayer:
    def __init__(
        self,
        conversation_manager: ConversationManager,
        followup_analyzer: FollowupAnalyzer,
        context_resolver: ContextResolver,
        result_resolver: ResultResolver,
    ) -> None:
        self._conversation_manager = conversation_manager
        self._followup_analyzer = followup_analyzer
        self._context_resolver = context_resolver
        self._result_resolver = result_resolver

    def process(
        self, question: str, raw_conversation: tuple[dict[str, Any], ...]
    ) -> ConversationDecision:
        recent_turns = self._conversation_manager.load_recent_turns(raw_conversation)
        analysis = self._followup_analyzer.analyze(question, recent_turns)

        classification = FollowupClassification(analysis.classification)
        requirement = ContextRequirement(analysis.context_requirement)

        if classification is FollowupClassification.OUT_OF_SCOPE:
            return ConversationDecision(
                classification=classification.value,
                confidence=analysis.confidence,
                next_action=NextAction.REJECT.value,
                scope_message=_OUT_OF_SCOPE_MESSAGE,
            )

        if classification is FollowupClassification.AMBIGUOUS:
            return ConversationDecision(
                classification=classification.value,
                confidence=analysis.confidence,
                next_action=NextAction.CLARIFICATION.value,
                clarification_message=_CLARIFICATION_MESSAGE,
            )

        if classification is FollowupClassification.INDEPENDENT:
            return ConversationDecision(
                classification=classification.value,
                confidence=analysis.confidence,
                next_action=NextAction.NL2SQL.value,
                context_requirement=ContextRequirement.NONE.value,
                resolved_question=question,
            )

        # QUESTION_FOLLOW_UP / SQL_FOLLOW_UP / RESULT_FOLLOW_UP all need a
        # referenced turn. Fail safe to clarification if the analyzer
        # named one that isn't actually in the candidate window.
        target_turn = self._find_turn(recent_turns, analysis.referenced_turn_id)
        if target_turn is None:
            return ConversationDecision(
                classification=FollowupClassification.AMBIGUOUS.value,
                confidence=analysis.confidence,
                next_action=NextAction.CLARIFICATION.value,
                clarification_message=_CLARIFICATION_MESSAGE,
            )

        fields = REQUIREMENT_FIELDS[requirement]
        retrieved = ContextRetriever.retrieve(target_turn, fields)

        if classification is FollowupClassification.RESULT_FOLLOW_UP:
            answer = self._result_resolver.resolve(question, retrieved)
            return ConversationDecision(
                classification=classification.value,
                confidence=analysis.confidence,
                next_action=NextAction.RESULT_RESOLVER.value,
                context_requirement=requirement.value,
                retrieved_turn_ids=(target_turn.turn_id,),
                direct_answer=answer,
            )

        # QUESTION_FOLLOW_UP or SQL_FOLLOW_UP -> resolve to a standalone
        # question, then hand off to the existing NL2SQL pipeline.
        resolved_question = self._context_resolver.resolve(question, retrieved)
        return ConversationDecision(
            classification=classification.value,
            confidence=analysis.confidence,
            next_action=NextAction.NL2SQL.value,
            context_requirement=requirement.value,
            retrieved_turn_ids=(target_turn.turn_id,),
            resolved_question=resolved_question,
        )

    @staticmethod
    def _find_turn(turns, turn_id: str | None):
        if turn_id is None:
            return turns[-1] if turns else None
        for turn in turns:
            if turn.turn_id == turn_id:
                return turn
        return turns[-1] if turns else None
