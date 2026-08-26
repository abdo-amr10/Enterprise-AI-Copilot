from typing import Any
from copy import deepcopy

from src.application.services.semantic_layer.validation.semantic_layer_auto_fixer import (
    SemanticLayerAutoFixer,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)


class SemanticLayerValidationPipeline:
    """Validate and optionally auto-fix an unpersisted Semantic Layer draft.

    Coordinates deterministic validation against the authoritative schema and relationships.
    If validation issues are found, delegates to SemanticLayerAutoFixer up to max_fix_attempts.
    """

    def __init__(
        self,
        validator: SemanticLayerValidator,
        auto_fixer: SemanticLayerAutoFixer,
        max_fix_attempts: int = 2,
    ) -> None:
        """Initialize the validation pipeline.

        Args:
            validator: Deterministic semantic layer validator.
            auto_fixer: LLM-assisted auto-fixer for repairing validation defects.
            max_fix_attempts: Maximum auto-fix attempts before returning failed validation.

        Raises:
            ValueError: If max_fix_attempts is negative.
        """
        if max_fix_attempts < 0:
            raise ValueError(
                "max_fix_attempts cannot be negative."
            )

        self._validator = validator
        self._auto_fixer = auto_fixer
        self._max_fix_attempts = max_fix_attempts

    def run(
        self,
        draft: dict[str, Any],
        schema: dict[str, Any],
        relationships: list[dict[str, Any]],
        has_semantic_context: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate and repair a Semantic Layer draft.

        Args:
            draft: Unpersisted semantic layer draft dictionary.
            schema: Authoritative physical database schema.
            relationships: Approved table relationships list.
            has_semantic_context: Whether documentation/glossary context was provided.

        Returns:
            A tuple of (validated_draft_or_current, validation_result_dict).
        """

        current = draft

        for attempt in range(self._max_fix_attempts + 1):

            validation = self._validator.validate(
                draft=current,
                schema=schema,
                relationships=relationships,
                has_semantic_context=has_semantic_context,
            )

            if validation["status"] == "passed":
                validated_draft = deepcopy(current)
                metadata = validated_draft.setdefault("metadata", {})
                metadata["validated"] = True
                metadata["status"] = "validated"
                metadata["human_review_required"] = True
                return validated_draft, validation

            if attempt == self._max_fix_attempts:
                return current, validation

            current = self._auto_fixer.fix(
                draft=current,
                validation=validation,
                schema=schema,
                relationships=relationships,
            )

        raise RuntimeError(
            "Validation pipeline reached an unexpected state."
        )
