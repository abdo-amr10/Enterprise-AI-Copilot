"""Internal HTTP endpoints for Semantic Layer AI operations.

The Backend owns uploads, revision persistence, status changes, and the
public ``/api/v1/semantic-layer/*`` contract.  These endpoints only execute
the AI-owned work after the Backend has resolved the source files and (for an
incremental change) the approved base revision.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_semantic_generation_pipeline,
    get_semantic_retrieval_pipeline,
    get_semantic_review_pipeline,
    get_semantic_validation_pipeline,
)
from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    AffectedObject,
    SemanticLayerGenerationRequest,
)
from src.application.dto.backend.copilot.semantic_retrieval_request import (
    SemanticRetrievalRequest,
)
from src.application.pipelines.context_retrieval.semantic_retrieval_pipeline import (
    SemanticRetrievalPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_generation_pipeline import (
    SemanticLayerGenerationPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_review_pipeline import (
    SemanticLayerReviewPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)

router = APIRouter(prefix="/internal/semantic", tags=["semantic"])


@router.post("/retrieve")
def retrieve(
    request: dict,
    pipeline: SemanticRetrievalPipeline = Depends(get_semantic_retrieval_pipeline),
):
    retrieval_request = SemanticRetrievalRequest(
        question=request["question"],
        conversation=tuple(request.get("conversation", [])),
        top_k=request.get("top_k"),
    )

    return pipeline.run(retrieval_request).to_dict()


def _required_object(request: dict[str, Any], key: str) -> dict[str, Any]:
    value = request.get(key)
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=422,
            detail=f"{key} must be an object.",
        )
    return value


def _required_string(request: dict[str, Any], key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(
            status_code=422,
            detail=f"{key} must be a non-empty string.",
        )
    return value


def _handle_contract_error(error: ValueError) -> None:
    """Convert application DTO validation failures to a client error."""

    raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/generate-draft")
def generate_draft(
    request: dict[str, Any],
    pipeline: SemanticLayerGenerationPipeline = Depends(
        get_semantic_generation_pipeline
    ),
) -> dict[str, Any]:
    """Generate an identity-assigned draft, without persisting it.

    ``resolvedSources`` must contain the already-loaded source content.  For
    FullRebuild it requires ``schema`` and ``relationships``.  For
    Incremental, ``baseSemanticLayer`` is the approved revision fetched by
    the Backend.  ``sourceFileIds`` remains part of the request for lineage,
    but the AI runtime deliberately does not fetch files from Backend storage.
    """

    try:
        affected_objects = tuple(
            AffectedObject(
                section=_required_string(item, "section"),
                id=_required_string(item, "id"),
            )
            for item in request.get("affectedObjects", [])
        )
        generation_request = SemanticLayerGenerationRequest(
            trigger_type=_required_string(request, "triggerType"),
            semantic_layer_id=_required_string(request, "semanticLayerId"),
            source_file_ids=_required_object(request, "sourceFileIds"),
            base_revision_id=request.get("baseRevisionId"),
            affected_objects=affected_objects,
        )
        sources = _required_object(request, "resolvedSources")
        base_semantic_layer = request.get("baseSemanticLayer")
        if base_semantic_layer is not None and not isinstance(
            base_semantic_layer, dict
        ):
            raise ValueError("baseSemanticLayer must be an object when provided.")

        draft = pipeline.run(
            request=generation_request,
            sources=sources,
            base_semantic_layer=base_semantic_layer,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required field: {error.args[0]}.",
        ) from error
    except (TypeError, ValueError) as error:
        _handle_contract_error(error)

    response: dict[str, Any] = {"status": "Success", "draft": draft}
    if generation_request.trigger_type == "Incremental":
        response["affectedObjects"] = [
            affected_object.to_dict() for affected_object in affected_objects
        ]
    return response


@router.post("/validate")
def validate_draft(
    request: dict[str, Any],
    pipeline: SemanticLayerValidationPipeline = Depends(
        get_semantic_validation_pipeline
    ),
) -> dict[str, Any]:
    """Validate and, when needed, auto-fix an unpersisted draft."""

    draft = _required_object(request, "draft")
    schema = _required_object(request, "schema")
    final_draft, validation = pipeline.run(draft=draft, schema=schema)
    return {
        "status": "Success",
        "draft": final_draft,
        "validation": validation,
    }


@router.post("/review")
def review_draft(
    request: dict[str, Any],
    pipeline: SemanticLayerReviewPipeline = Depends(get_semantic_review_pipeline),
) -> dict[str, Any]:
    """Apply a Backend-authenticated human decision to a validated draft."""

    try:
        draft = _required_object(request, "draft")
        validation = _required_object(request, "validation")
        decision = _required_string(request, "decision")
        if decision not in {"Approve", "Reject"}:
            raise ValueError("decision must be Approve or Reject.")
        comments = request.get("comments", "")
        if not isinstance(comments, str):
            raise ValueError("comments must be a string when provided.")
        if decision == "Reject" and not comments.strip():
            raise ValueError("comments are required when rejecting a revision.")
        reviewed_draft, review = pipeline.run(
            draft=draft,
            validation=validation,
            decision=decision,
            reviewer=_required_string(request, "reviewerId"),
            comments=comments,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required field: {error.args[0]}.",
        ) from error
    except (TypeError, ValueError) as error:
        _handle_contract_error(error)

    return {
        "status": "Approved" if review["decision"] == "approve" else "Rejected",
        "draft": reviewed_draft,
        "review": review,
    }
