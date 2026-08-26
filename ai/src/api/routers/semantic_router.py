"""Internal HTTP endpoints for Semantic Layer AI operations.

The Backend owns uploads, revision persistence, status changes, and the
public ``/api/v1/semantic-layer/*`` contract. These endpoints retrieve
Backend-owned source files by ID and perform only AI-owned processing.
"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_semantic_retrieval_pipeline,
)
from src.api.generation_validation_dependencies import (
    get_semantic_generation_pipeline,
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
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)
from src.infrastructure.backend.backend_semantic_client import BackendSemanticClient
from src.api.contracts import (
    SemanticGenerateRequest,
    SemanticRetrieveRequest,
    SemanticReviewRequest,
    SemanticValidateRequest,
)

router = APIRouter(prefix="/internal/semantic", tags=["semantic"])


@router.post("/retrieve")
def retrieve(
    request: SemanticRetrieveRequest,
    pipeline: SemanticRetrievalPipeline = Depends(get_semantic_retrieval_pipeline),
):
    if request.conversation:
        raise HTTPException(status_code=422, detail="conversation is not supported by the current semantic retrieval runtime.")
    retrieval_request = SemanticRetrievalRequest(question=request.question, conversation=(), top_k=request.top_k)

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


def _present_source_file_ids(request: dict[str, Any]) -> dict[str, str]:
    """Drop only optional null IDs while keeping schema mandatory downstream."""

    source_file_ids = _required_object(request, "sourceFileIds")
    return {
        source_type: file_id
        for source_type, file_id in source_file_ids.items()
        if file_id is not None
    }


def _handle_contract_error(error: ValueError) -> None:
    """Convert application DTO validation failures to a client error."""

    raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/generate-draft")
def generate_draft(
    request: SemanticGenerateRequest,
    pipeline: SemanticLayerGenerationPipeline = Depends(
        get_semantic_generation_pipeline
    ),
) -> dict[str, Any]:
    """Generate an unpersisted draft from Backend-owned source IDs.

    The Backend creates ``revisionId`` only after it persists this draft, so it
    is deliberately not part of this request contract.
    """

    try:
        body = request.model_dump()
        affected_objects = tuple(
            AffectedObject(
                section=_required_string(item, "section"),
                action=item.get("action", "update"),
                id=item.get("id"),
                name=item.get("name"),
            )
            for item in body.get("affectedObjects", [])
        )
        generation_request = SemanticLayerGenerationRequest(
            trigger_type=_required_string(body, "triggerType"),
            semantic_layer_id=_required_string(body, "semanticLayerId"),
            source_file_ids=_present_source_file_ids(body),
            base_revision_id=body.get("baseRevisionId"),
            affected_objects=affected_objects,
        )
        sources = BackendSemanticClient().load_generation_sources(
            generation_request.source_file_ids
        )
        _validate_resolved_sources(generation_request.trigger_type, sources)
        base_semantic_layer = body.get("baseSemanticLayer")
        if generation_request.trigger_type == "Incremental" and base_semantic_layer is None:
            if not generation_request.base_revision_id:
                raise ValueError("baseRevisionId is required for Incremental generation.")
            base_semantic_layer = BackendSemanticClient().load_revision(
                generation_request.base_revision_id
            )
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
    except (TypeError, ValueError, RuntimeError) as error:
        _handle_contract_error(error)

    # The current Backend persists this response directly as ContentJson and
    # reads semantic-layer sections from the root object. Return the draft
    # itself rather than an HTTP wrapper such as {"status": "Success",
    # "draft": ...}; otherwise revisions deserialize as empty collections.
    response = dict(draft)
    # Preserve camelCase sections if the generation pipeline already emitted
    # them; only translate the internal snake_case names when present.
    if "business_rules" in response:
        response["businessRules"] = response.pop("business_rules")
    else:
        response.setdefault("businessRules", [])
    if "validation_issues" in response:
        response["validationIssues"] = response.pop("validation_issues")
    else:
        response.setdefault("validationIssues", [])
    return response


@router.post("/validate")
def validate_draft(
    request: SemanticValidateRequest,
    pipeline: SemanticLayerValidationPipeline = Depends(
        get_semantic_validation_pipeline
    ),
) -> dict[str, Any]:
    """Validate a supplied draft or acknowledge the current Backend contract."""

    if request.draft is not None or request.schema is not None:
        if request.draft is None or request.schema is None:
            raise HTTPException(
                status_code=422,
                detail="draft and schema must be supplied together for validation.",
            )
        final_draft, validation = pipeline.run(
            draft=request.draft,
            schema=request.schema,
            relationships=request.relationships,
            has_semantic_context=bool(
                (request.documentation and request.documentation.strip())
                or (request.businessGlossary and request.businessGlossary.strip())
            ),
        )
        return {"status": "Success", "draft": final_draft, "validation": validation}

    if not request.revisionId:
        raise HTTPException(
            status_code=422,
            detail="revisionId or draft plus schema is required.",
        )

    return {
        "status": "Success",
        "revisionId": request.revisionId,
        "validation": {"status": "passed", "mode": "backend-acknowledgement"},
    }


@router.post("/review")
def review_draft(
    request: SemanticReviewRequest,
) -> dict[str, Any]:
    """Acknowledge the Backend-owned human review decision.

    The Backend performs authorization, records the reviewer and comments,
    and changes the persisted revision status after this call succeeds.
    """
    return {
        "status": "Approved" if request.decision == "Approve" else "Rejected",
        "revisionId": request.revisionId,
    }


def _validate_resolved_sources(trigger_type: str, sources: dict[str, Any]) -> None:
    """Fail at the HTTP boundary before builders see malformed source data."""
    if trigger_type == "FullRebuild":
        if not isinstance(sources.get("schema"), dict):
            raise ValueError("Backend schema source must be an object for FullRebuild.")
        if not isinstance(sources.get("relationships"), list):
            raise ValueError("Backend schema relationships must be a list for FullRebuild.")
