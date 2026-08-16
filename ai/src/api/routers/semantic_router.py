"""HTTP entry point for `POST /internal/semantic/retrieve`."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.dependencies import get_semantic_retrieval_pipeline
from src.application.dto.backend.copilot.semantic_retrieval_request import (
    SemanticRetrievalRequest,
)
from src.application.pipelines.context_retrieval.semantic_retrieval_pipeline import (
    SemanticRetrievalPipeline,
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
