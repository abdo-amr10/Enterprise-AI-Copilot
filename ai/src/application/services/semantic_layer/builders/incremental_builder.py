import json
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.semantic_layer_incremental_prompt import (
    INCREMENTAL_PROMPT,
)


class IncrementalBuilder:
    """Build an incremental Semantic Layer patch."""

    _MERGEABLE_SECTIONS = {
        "entities",
        "relationships",
        "measures",
        "dimensions",
        "business_rules",
    }

    _VALID_ACTIONS = {
        "add",
        "update",
        "delete",
    }

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def build(
        self,
        base_semantic_layer: dict[str, Any],
        affected_objects: list[dict[str, Any]],
        updated_sources: dict[str, Any],
    ) -> SemanticLayerBuildResponse:
        """Generate an incremental Semantic Layer patch."""

        self._validate_base_semantic_layer(
            base_semantic_layer,
        )

        self._validate_affected_objects(
            affected_objects,
        )

        self._validate_updated_sources(
            updated_sources,
        )

        prompt = self._build_prompt(
            base_semantic_layer=base_semantic_layer,
            affected_objects=affected_objects,
            updated_sources=updated_sources,
        )

        response: GenerationResponse = self._llm_client.generate(
            GenerationRequest(prompt=prompt)
        )

        semantic_layer = self._output_parser.parse(
            response.text,
        )

        return SemanticLayerBuildResponse(
            semantic_layer=semantic_layer,
        )

    @staticmethod
    def _build_prompt(
        base_semantic_layer: dict[str, Any],
        affected_objects: list[dict[str, Any]],
        updated_sources: dict[str, Any],
    ) -> str:
        """Build the Incremental LLM prompt."""

        return f"""
{INCREMENTAL_PROMPT}

BASE APPROVED SEMANTIC LAYER:
{json.dumps(
    base_semantic_layer,
    indent=2,
    ensure_ascii=False,
)}

AFFECTED SEMANTIC OBJECTS:
{json.dumps(
    affected_objects,
    indent=2,
    ensure_ascii=False,
)}

UPDATED SOURCES:
{json.dumps(
    updated_sources,
    indent=2,
    ensure_ascii=False,
)}
""".strip()

    @classmethod
    def _validate_base_semantic_layer(
        cls,
        base_semantic_layer: dict[str, Any],
    ) -> None:
        """Validate the approved baseline before generation."""

        if not isinstance(base_semantic_layer, dict):
            raise ValueError(
                "base_semantic_layer must be a dictionary."
            )

        if not base_semantic_layer:
            raise ValueError(
                "base_semantic_layer cannot be empty."
            )

        if "metadata" not in base_semantic_layer:
            raise ValueError(
                "base_semantic_layer must contain metadata."
            )

        for section in cls._MERGEABLE_SECTIONS:
            value = base_semantic_layer.get(section, [])

            if not isinstance(value, list):
                raise ValueError(
                    f"base_semantic_layer section '{section}' must be a list."
                )

    @classmethod
    def _validate_affected_objects(
        cls,
        affected_objects: list[dict[str, Any]],
    ) -> None:
        """Validate the incremental semantic-object scope."""

        if not isinstance(affected_objects, list):
            raise ValueError(
                "affected_objects must be a list."
            )

        if not affected_objects:
            raise ValueError(
                "affected_objects cannot be empty for Incremental generation."
            )

        seen_operations: set[tuple[str, str, str | None, str | None]] = set()

        for item in affected_objects:
            if not isinstance(item, dict):
                raise ValueError(
                    "Each affected object must be a dictionary."
                )

            section = item.get("section")
            action = item.get("action")
            object_id = item.get("id")
            name = item.get("name")

            if section not in cls._MERGEABLE_SECTIONS:
                raise ValueError(
                    f"Unsupported affected-object section: '{section}'."
                )

            if action not in cls._VALID_ACTIONS:
                raise ValueError(
                    "Affected object action must be add, update, or delete."
                )

            if action in {"update", "delete"}:
                if not isinstance(object_id, str) or not object_id.strip():
                    raise ValueError(
                        "Affected object id is required for update and delete."
                    )

                if name is not None and not isinstance(name, str):
                    raise ValueError(
                        "Affected object name must be a string when provided."
                    )

            if action == "add":
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(
                        "Affected object name is required for add."
                    )

                if object_id is not None:
                    raise ValueError(
                        "Affected object id must not be supplied for add."
                    )

            operation_key = (
                section,
                action,
                object_id,
                name,
            )

            if operation_key in seen_operations:
                raise ValueError(
                    "Duplicate affected-object operation detected: "
                    f"{operation_key}."
                )

            seen_operations.add(operation_key)

    @staticmethod
    def _validate_updated_sources(
        updated_sources: dict[str, Any],
    ) -> None:
        """Validate the authoritative source container."""

        if not isinstance(updated_sources, dict):
            raise ValueError(
                "updated_sources must be a dictionary."
            )

        if "schema" not in updated_sources:
            raise ValueError(
                "updated_sources must contain authoritative schema metadata."
            )

        if "relationships" not in updated_sources:
            raise ValueError(
                "updated_sources must contain authoritative relationship metadata."
            )