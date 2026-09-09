"""Conversation Turn Retriever.

Reuses the existing EmbeddingService (the same component that powers
semantic-layer schema retrieval) to find the most relevant PAST question
in this conversation's full execution_history -- not just the most
recent one. This is what makes "did I already ask something like this?"
work no matter how long ago it was asked.

Used by ConversationRouter for two purposes:
  1. Near-duplicate detection: a high-similarity match to a past
     successful execution can be treated like an exact replay hit.
  2. Picking the right prior turn for ContinuationResolver when a
     follow-up modifier ("only Egypt", "sort that by date") needs to be
     applied to something other than the literal last turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from src.application.services.conversation.state.conversation_state import ExecutionRecord

MAX_HISTORY_TO_EMBED = 200
DEFAULT_SIMILARITY_THRESHOLD = 0.86


class EmbeddingClient(Protocol):
    def encode_query(self, text: str): ...
    def encode_documents(self, texts): ...


@dataclass(frozen=True)
class TurnMatch:
    record: ExecutionRecord
    score: float


class ConversationTurnRetriever:
    def __init__(
        self,
        embedding_service: EmbeddingClient,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        self._embedding_service = embedding_service
        self._similarity_threshold = similarity_threshold

    def find_best_match(
        self, question: str, execution_history: list[ExecutionRecord]
    ) -> Optional[TurnMatch]:
        """Returns the closest-matching past execution, or None if nothing
        clears the similarity threshold (or no history has a stored question)."""
        candidates = [
            record for record in execution_history[-MAX_HISTORY_TO_EMBED:]
            if record.user_question
        ]
        if not candidates:
            return None

        query_vector = self._embedding_service.encode_query(question)
        vectors = self._embedding_service.encode_documents(
            [record.user_question for record in candidates]
        )

        best_record, best_score = None, -1.0
        for record, vector in zip(candidates, vectors):
            score = float(query_vector @ vector)
            if score > best_score:
                best_record, best_score = record, score

        if best_record is None or best_score < self._similarity_threshold:
            return None
        return TurnMatch(record=best_record, score=best_score)
