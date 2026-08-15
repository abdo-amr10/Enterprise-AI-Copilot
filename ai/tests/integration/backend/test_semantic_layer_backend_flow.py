from unittest.mock import Mock

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_review_request import (
    SemanticLayerReviewRequest,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient
from src.infrastructure.backend.clients.semantic_layer_generation_client import (
    SemanticLayerGenerationClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_revision_client import (
    SemanticLayerRevisionClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_revision_update_client import (
    SemanticLayerSubmitClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_review_client import (
    SemanticLayerReviewClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_status_client import (
    SemanticLayerStatusClientImpl,
)


def test_semantic_layer_backend_clients_flow() -> None:
    """Verify the generate, review, and submit API contracts end to end."""

    http_client = Mock(spec=BackendHttpClient)
    semantic_layer_id = "sl-001"
    revision_id = "rev-001"

    http_client.post.side_effect = [
        {
            "status": "DraftGenerated",
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "regeneratedObjectsCount": 4,
            "buildTimestamp": "2026-08-15T14:30:00Z",
            "lastRegenerationType": "FullRebuild",
        },
        {
            "status": "Submitted",
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "message": "Revision submitted for validation.",
        },
        {
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "status": "Approved",
            "version": "v1.0",
            "approvedBy": "usr-123",
            "approvedAt": "2026-08-15T15:30:00Z",
        },
    ]
    http_client.get.side_effect = [
        {
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "status": "PendingReview",
            "version": "draft",
            "buildTimestamp": "2026-08-15T14:30:00Z",
            "lastRegenerationType": "FullRebuild",
            "content": "{\"entities\": []}",
            "createdAt": "2026-08-15T14:30:00Z",
        },
        {
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "status": "Approved",
            "version": "v1.0",
            "buildTimestamp": "2026-08-15T14:30:00Z",
            "lastRegenerationType": "FullRebuild",
        },
    ]

    generation_client = SemanticLayerGenerationClientImpl(http_client)
    revision_client = SemanticLayerRevisionClientImpl(http_client)
    submit_client = SemanticLayerSubmitClientImpl(http_client)
    review_client = SemanticLayerReviewClientImpl(http_client)
    status_client = SemanticLayerStatusClientImpl(http_client)

    generation_response = generation_client.generate_draft(
        SemanticLayerGenerationRequest(
            trigger_type="FullRebuild",
            semantic_layer_id=semantic_layer_id,
            source_file_ids={"schema": "file-001"},
        )
    )
    assert generation_response.semantic_layer_id == semantic_layer_id

    revision_response = revision_client.get_revision(
        semantic_layer_id,
        revision_id,
    )
    assert revision_response.status == "PendingReview"

    submit_response = submit_client.submit(semantic_layer_id, revision_id)
    assert submit_response.status == "Submitted"

    review_response = review_client.review(
        SemanticLayerReviewRequest(
            semantic_layer_id=semantic_layer_id,
            revision_id=revision_id,
            decision="Approve",
        )
    )
    assert review_response.status == "Approved"

    status_response = status_client.get_status(semantic_layer_id)
    assert status_response.status == "Approved"

    http_client.get.assert_any_call(
        f"/api/v1/semantic-layer/{semantic_layer_id}/revisions/{revision_id}"
    )
    http_client.post.assert_any_call(
        f"/api/v1/semantic-layer/{semantic_layer_id}/revisions/{revision_id}/submit",
        {},
    )
    http_client.get.assert_any_call(
        f"/api/v1/semantic-layer/{semantic_layer_id}/status"
    )
