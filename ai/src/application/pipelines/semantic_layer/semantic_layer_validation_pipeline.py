from typing import Any
from copy import deepcopy

from src.application.services.semantic_layer.validation.semantic_layer_auto_fixer import (
    SemanticLayerAutoFixer,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)


class SemanticLayerValidationPipeline:
    """Validate and optionally auto-fix a Semantic Layer draft."""

    def __init__(
        self,
        validator: SemanticLayerValidator,
        auto_fixer: SemanticLayerAutoFixer,
        max_fix_attempts: int = 2,
    ) -> None:

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
    ) -> tuple[dict[str, Any], dict[str, Any]]:

        current = draft

        for attempt in range(self._max_fix_attempts + 1):

            validation = self._validator.validate(
                draft=current,
                schema=schema,
                relationships=relationships,
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
