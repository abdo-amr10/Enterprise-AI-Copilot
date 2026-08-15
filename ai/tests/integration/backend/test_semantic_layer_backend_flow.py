from unittest.mock import Mock

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_review_request import (
    SemanticLayerReviewRequest,
)
from src.application.dto.backend.semantic_layer.upload_sources_request import (
    UploadSourcesRequest,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient
from src.infrastructure.backend.clients.semantic_layer_generation_client import (
    SemanticLayerGenerationClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_revision_client import (
    SemanticLayerRevisionClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_review_client import (
    SemanticLayerReviewClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_source_client import (
    SemanticLayerSourceClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_status_client import (
    SemanticLayerStatusClientImpl,
)
from src.infrastructure.backend.clients.semantic_layer_revision_update_client import (
    SemanticLayerSubmitClientImpl,
)


def test_semantic_layer_backend_clients_flow() -> None:
    """Verify the complete Semantic Layer client flow using a mocked Backend."""

    http_client = Mock(spec=BackendHttpClient)

    # Mock responses returned by the Backend.
    http_client.post.side_effect = [
        {
            "status": "SourcesLoaded",
            "databaseConfigId": "db-erp-prod-01",
        },
        {
            "status": "DraftGenerated",
            "revisionId": "revision-001",
        },
        {
            "status": "Submitted",
            "revisionId": "revision-001",
        },
        {
            "revisionId": "revision-001",
            "status": "Approved",
        },
    ]

    http_client.get.side_effect = [
        {
            "revisionId": "revision-001",
            "status": "PendingReview",
        },
        {
            "status": "Approved",
            "version": "v1",
            "lastRegenerationType": "FullRebuild",
        },
    ]

    source_client = SemanticLayerSourceClientImpl(http_client)
    generation_client = SemanticLayerGenerationClientImpl(http_client)
    revision_client = SemanticLayerRevisionClientImpl(http_client)
    submit_client = SemanticLayerSubmitClientImpl(http_client)
    review_client = SemanticLayerReviewClientImpl(http_client)
    status_client = SemanticLayerStatusClientImpl(http_client)

    # 1. Prepare Semantic Layer sources.
    source_response = source_client.prepare_sources(
        UploadSourcesRequest(
            database_config_id="db-erp-prod-01",
            trigger_type="FullRebuild",
            affected_objects=None,
        )
    )

    assert source_response.status == "SourcesLoaded"
    assert source_response.database_config_id == "db-erp-prod-01"

    # 2. Generate Semantic Layer draft.
    generation_response = generation_client.generate_draft(
        SemanticLayerGenerationRequest(
            trigger_type="FullRebuild",
            affected_objects=None,
        )
    )

    assert generation_response.status == "DraftGenerated"
    assert generation_response.revision_id

    revision_id = generation_response.revision_id

    # 3. Retrieve generated revision.
    revision_response = revision_client.get_revision(revision_id)

    assert revision_response.revision_id == revision_id
    assert revision_response.status == "PendingReview"

    # 4. Submit revision.
    submit_response = submit_client.submit(revision_id)

    assert submit_response.status == "Submitted"
    assert submit_response.revision_id == revision_id

    # 5. Approve revision.
    review_response = review_client.review(
        SemanticLayerReviewRequest(
            revision_id=revision_id,
            decision="Approve",
            comments=None,
        )
    )

    assert review_response.revision_id == revision_id
    assert review_response.status == "Approved"

    # 6. Verify active Semantic Layer status.
    status_response = status_client.get_status()

    assert status_response.status == "Approved"
    assert status_response.version
    assert status_response.last_regeneration_type in {
        "FullRebuild",
        "Incremental",
    }
