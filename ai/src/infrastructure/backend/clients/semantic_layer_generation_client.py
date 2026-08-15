from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    SemanticLayerGenerationRequest,
)
from src.application.dto.backend.semantic_layer.semantic_layer_generation_response import (
    SemanticLayerGenerationResponse,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient


class SemanticLayerGenerationClientImpl:
    """Triggers Semantic Layer draft generation through the Backend API."""

    def __init__(self, http_client: BackendHttpClient) -> None:
        """Initialize the Semantic Layer generation client.

        Args:
            http_client: Shared HTTP client used to communicate
                with the Backend.
        """

        self._http_client = http_client

    def generate_draft(
        self,
        request: SemanticLayerGenerationRequest,
    ) -> SemanticLayerGenerationResponse:
        """Trigger Semantic Layer draft generation.

        Args:
            request: Generation configuration containing the Semantic
                Layer identifier, source files, and regeneration mode.

        Returns:
            Information about the generated Semantic Layer revision.
        """

        payload = {
            "semanticLayerId": request.semantic_layer_id,
            "triggerType": request.trigger_type,
            "sourceFileIds": dict(request.source_file_ids),
        }

        if request.trigger_type == "Incremental":
            payload["baseRevisionId"] = request.base_revision_id
            payload["affectedObjects"] = [
                affected_object.to_dict()
                for affected_object in request.affected_objects
            ]

        response = self._http_client.post(
            "/api/v1/semantic-layer/generate-draft",
            payload,
        )

        return SemanticLayerGenerationResponse(
            status=response["status"],
            semantic_layer_id=response["semanticLayerId"],
            revision_id=response["revisionId"],
            regenerated_objects_count=response[
                "regeneratedObjectsCount"
            ],
            build_timestamp=response["buildTimestamp"],
            last_regeneration_type=response[
                "lastRegenerationType"
            ],
            affected_objects=tuple(response.get("affectedObjects", ())),
        )
