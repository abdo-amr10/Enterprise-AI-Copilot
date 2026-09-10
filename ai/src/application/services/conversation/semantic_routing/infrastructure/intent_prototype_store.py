"""In-memory prototype embedding store for fast, lightweight semantic intent ranking."""

from __future__ import annotations

import logging
from typing import Mapping, Sequence

import numpy as np

from src.application.services.conversation.semantic_routing.configuration.prototype_catalog import (
    DEFAULT_PROTOTYPE_CATALOG,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)
from src.application.services.conversation.semantic_routing.infrastructure.embedding_provider import (
    IntentEmbeddingProvider,
)

logger = logging.getLogger(__name__)


class IntentPrototypeStore:
    """Precomputes and stores prototype embeddings in memory for low-latency scoring."""

    def __init__(
        self,
        embedding_provider: IntentEmbeddingProvider,
        catalog: Mapping[ConversationIntent, Sequence[str]] | None = None,
    ) -> None:
        self._provider = embedding_provider
        self._catalog = catalog or DEFAULT_PROTOTYPE_CATALOG
        self._intent_examples: dict[ConversationIntent, tuple[str, ...]] = {}
        self._intent_matrices: dict[ConversationIntent, np.ndarray] = {}
        self._is_initialized = False

    def ensure_initialized(self) -> None:
        """Precompute prototype embeddings once into memory."""
        if self._is_initialized:
            return

        logger.info("Initializing IntentPrototypeStore: precomputing prototype embeddings...")
        total_examples = 0
        for intent, examples in self._catalog.items():
            example_tuple = tuple(examples)
            if not example_tuple:
                continue
            matrix = self._provider.encode(example_tuple)
            self._intent_examples[intent] = example_tuple
            self._intent_matrices[intent] = matrix
            total_examples += len(example_tuple)

        self._is_initialized = True
        logger.info(
            "IntentPrototypeStore initialized with %d intents and %d prototype examples.",
            len(self._intent_matrices),
            total_examples,
        )

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def rank_intents(
        self,
        query_vector: np.ndarray,
    ) -> list[tuple[ConversationIntent, float, str]]:
        """Rank all intents against the query vector using in-memory cosine similarity."""
        self.ensure_initialized()

        results: list[tuple[ConversationIntent, float, str]] = []
        for intent, matrix in self._intent_matrices.items():
            if matrix.shape[0] == 0:
                continue
            # Cosine similarity via dot product since vectors are unit-normalized
            sims = np.dot(matrix, query_vector)
            best_idx = int(np.argmax(sims))
            best_score = float(sims[best_idx])
            best_example = self._intent_examples[intent][best_idx]
            results.append((intent, best_score, best_example))

        # Sort descending by best score
        results.sort(key=lambda x: x[1], reverse=True)
        return results
