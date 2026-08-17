"""Run semantic-layer validation and human-review workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)
from src.application.services.semantic_layer.review_manager import (
    HumanReviewManager,
)
from src.application.services.semantic_layer.validation.semantic_layer_auto_fixer import SemanticLayerAutoFixer
from src.infrastructure.llm.model_config import SEMANTIC_LAYER_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient

AI_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = AI_ROOT.parent

OUTPUT_DIR = AI_ROOT / "outputs" / "semantic_layer"

INITIAL_DRAFT_PATH = OUTPUT_DIR / "initial_draft.json"
CURRENT_DRAFT_PATH = OUTPUT_DIR / "current_draft.json"

SCHEMA_PATH = (
    PROJECT_ROOT
    / "docs"
    / "database_metadata"
    / "schema.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    """Load and return a JSON object from the given file."""

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in: {path}")

    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write a dictionary to a JSON file."""

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    """Run semantic-layer validation, auto-fix, and human review."""

    validator = SemanticLayerValidator()
    review_manager = HumanReviewManager()
    auto_fixer = SemanticLayerAutoFixer(OllamaClient(SEMANTIC_LAYER_CONFIG))

    schema = _load_json(SCHEMA_PATH)

    # Use the latest working draft when available.
    if CURRENT_DRAFT_PATH.exists():
        draft_path = CURRENT_DRAFT_PATH
    else:
        draft_path = INITIAL_DRAFT_PATH

    max_auto_fix_attempts = 2
    auto_fix_attempt = 0

    while True:
        draft = _load_json(draft_path)

        # ---------------------------------------------------------
        # 1. Automated validation
        # ---------------------------------------------------------
        validation = validator.validate(
            draft,
            schema,
        )

        _write_json(
            OUTPUT_DIR / "validation_result.json",
            validation,
        )

        print("\n=== Semantic Layer Validation ===")
        print(f"Status: {validation['status']}")
        print(
            f"Errors: "
            f"{validation['summary']['error_count']}"
        )
        print(
            f"Warnings: "
            f"{validation['summary']['warning_count']}"
        )

        # ---------------------------------------------------------
        # 2. Auto-fix validation errors
        # ---------------------------------------------------------
        if validation["status"] == "failed":

            if auto_fix_attempt >= max_auto_fix_attempts:
                print(
                    "\nMaximum auto-fix attempts reached."
                )
                print(
                    "Manual correction is required."
                )
                return

            print(
                "\nValidation failed."
            )
            print(
                "Auto-fix attempt "
                f"{auto_fix_attempt + 1}/"
                f"{max_auto_fix_attempts}"
            )

            auto_fix_attempt += 1
            corrected_draft = auto_fixer.fix(draft=draft, validation=validation, schema=schema)
            _write_json(CURRENT_DRAFT_PATH, corrected_draft)
            draft_path = CURRENT_DRAFT_PATH
            continue

        # ---------------------------------------------------------
        # 3. Validation passed
        # ---------------------------------------------------------
        print(
            "\nValidation passed."
        )

        _write_json(
            CURRENT_DRAFT_PATH,
            draft,
        )

        # ---------------------------------------------------------
        # 4. Human review
        # ---------------------------------------------------------
        print("\n=== Human Review ===")

        decision = input(
            "Enter decision [approve/reject]: "
        ).strip().lower()

        reviewer = input(
            "Reviewer name: "
        ).strip()

        comments = input(
            "Comments: "
        ).strip()

        reviewed_draft, review_result = (
            review_manager.review(
                draft,
                validation,
                decision=decision,
                reviewer=reviewer,
                comments=comments,
            )
        )

        _write_json(
            OUTPUT_DIR / "review_result.json",
            review_result,
        )

        # ---------------------------------------------------------
        # 5. Human approved
        # ---------------------------------------------------------
        if decision == "approve":

            _write_json(
                OUTPUT_DIR
                / "approved_semantic_layer.json",
                reviewed_draft,
            )

            print(
                "\nSemantic Layer approved successfully."
            )
            print(
                "approved_semantic_layer.json has been created."
            )

            return

        # ---------------------------------------------------------
        # 6. Human rejected
        # ---------------------------------------------------------
        if decision == "reject":

            _write_json(
                CURRENT_DRAFT_PATH,
                reviewed_draft,
            )

            print(
                "\nSemantic Layer rejected."
            )

            print(
                "\nReviewer comments:"
            )
            print(
                comments or "(No comments provided.)"
            )

            print(
                "\nPlease manually edit:"
            )
            print(
                CURRENT_DRAFT_PATH
            )

            input(
                "\nAfter correcting the draft, "
                "press Enter to validate again..."
            )

            # Reset auto-fix attempts for the new
            # human-corrected version.
            auto_fix_attempt = 0

            draft_path = CURRENT_DRAFT_PATH

            continue

if __name__ == "__main__":
    main()
