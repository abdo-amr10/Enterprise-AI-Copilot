"""Generate identifiers for Semantic Layers and their revisions."""

from __future__ import annotations

from uuid import uuid4


class SemanticLayerIdGenerator:
    """Generate Semantic Layer and revision identifiers.

    This is the single authoritative source of Semantic Layer and
    revision identifiers in the application. No other component may
    generate these IDs directly.
    """

    @staticmethod
    def generate_semantic_layer_id() -> str:
        """Generate a new Semantic Layer identifier."""

        return f"sl-{uuid4().hex}"

    @staticmethod
    def generate_revision_id() -> str:
        """Generate a new Semantic Layer revision identifier."""

        return f"rev-{uuid4().hex}"
