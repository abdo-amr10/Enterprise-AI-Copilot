from typing import Any

from src.application.dto.backend.semantic_layer.semantic_layer_source_response import (
    SemanticLayerSourceResponse,
)
from src.application.dto.backend.semantic_layer.source_file import SourceFile
from src.application.dto.backend.semantic_layer.upload_sources_request import (
    UploadSourcesRequest,
)
from src.application.dto.backend.semantic_layer.upload_sources_response import (
    UploadSourcesResponse,
)
from src.infrastructure.backend.backend_http_client import BackendHttpClient


class SemanticLayerSourceClientImpl:
    """Handles Semantic Layer source communication with the Backend."""

    def __init__(self, http_client: BackendHttpClient) -> None:
        """Initialize the Semantic Layer source client.

        Args:
            http_client: Shared HTTP client used to communicate
                with the Backend.
        """

        self._http_client = http_client

    def prepare_sources(
        self,
        request: UploadSourcesRequest,
    ) -> UploadSourcesResponse:
        """Upload Semantic Layer source files to the Backend.

        Args:
            request: Source files and Semantic Layer metadata.

        Returns:
            Backend response containing the Semantic Layer identifier
            and the identifiers of the stored source files.
        """

        files: dict[str, tuple[str, Any]] = {
            "schemaFile": request.schema_file,
        }

        if request.documentation_file is not None:
            files["documentationFile"] = request.documentation_file

        if request.glossary_file is not None:
            files["glossaryFile"] = request.glossary_file

        if request.sample_data_file is not None:
            files["sampleDataFile"] = request.sample_data_file

        data: dict[str, str] = {
            "name": request.name,
        }

        if request.description is not None:
            data["description"] = request.description

        response = self._http_client.post_multipart(
            "/api/v1/semantic-layer/upload",
            data=data,
            files=files,
        )

        return self._parse_upload_response(response)

    def get_source(
        self,
        file_id: str,
    ) -> SemanticLayerSourceResponse:
        """Retrieve a stored Semantic Layer source file.

        Args:
            file_id: Backend-managed identifier of the source file.

        Returns:
            The source file metadata and content.

        Raises:
            ValueError: If the file ID is empty.
        """

        if not file_id.strip():
            raise ValueError("file_id cannot be empty.")

        response = self._http_client.get(
            f"/api/v1/semantic-layer/files/{file_id}"
        )

        return SemanticLayerSourceResponse(
            file_id=response["fileId"],
            file_name=response["fileName"],
            file_type=response["fileType"],
            content=response["content"],
        )

    @staticmethod
    def _parse_upload_response(
        response: dict[str, Any],
    ) -> UploadSourcesResponse:
        """Convert the Backend upload response into an application DTO.

        Args:
            response: Raw JSON response returned by the Backend.

        Returns:
            Parsed upload response.
        """

        raw_sources = response.get("sources", {})
        sources: dict[str, SourceFile | None] = {}

        if isinstance(raw_sources, dict):
            backend_mapping = {
                "schema": ("schemaFileId", "schema"),
                "documentation": ("documentationFileId", "documentation"),
                "glossary": ("glossaryFileId", "glossary"),
                "sampleData": ("sampleDataFileId", "sampleData"),
            }
            has_file_id_keys = any(
                field_name in raw_sources
                for field_name, _ in backend_mapping.values()
            )

            if has_file_id_keys:
                for source_name, (field_name, file_type) in backend_mapping.items():
                    file_id = raw_sources.get(field_name)
                    if file_id is not None and str(file_id).strip():
                        sources[source_name] = SourceFile(
                            file_id=str(file_id),
                            file_type=file_type,
                        )
                    else:
                        sources[source_name] = None
            else:
                for source_type, source_data in raw_sources.items():
                    if isinstance(source_data, dict):
                        sources[source_type] = SourceFile(
                            file_id=source_data.get("fileId", ""),
                            file_type=source_data.get("fileType", source_type),
                        )
                    elif isinstance(source_data, str) and source_data.strip():
                        sources[source_type] = SourceFile(
                            file_id=source_data,
                            file_type=source_type,
                        )
                    else:
                        sources[source_type] = None

        return UploadSourcesResponse(
            status=response.get("status", ""),
            semantic_layer_id=response.get("semanticLayerId", ""),
            name=response.get("name", ""),
            description=response.get("description"),
            sources=sources,
        )
