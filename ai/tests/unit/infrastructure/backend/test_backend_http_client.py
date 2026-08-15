from unittest.mock import Mock, patch

import pytest
import requests

from src.infrastructure.backend.backend_http_client import BackendHttpClient


class TestBackendHttpClient:
    """Test the shared HTTP client used for Backend communication."""

    def test_initialization_rejects_empty_base_url(self) -> None:
        """Ensure an empty Backend base URL is rejected."""

        with pytest.raises(ValueError, match="base_url cannot be empty"):
            BackendHttpClient(
                base_url="",
                token="test-token",
            )

    def test_initialization_rejects_empty_token(self) -> None:
        """Ensure an empty authentication token is rejected."""

        with pytest.raises(ValueError, match="token cannot be empty"):
            BackendHttpClient(
                base_url="http://localhost:5000",
                token="",
            )

    def test_initialization_rejects_invalid_timeout(self) -> None:
        """Ensure a non-positive timeout is rejected."""

        with pytest.raises(
            ValueError,
            match="timeout must be greater than zero",
        ):
            BackendHttpClient(
                base_url="http://localhost:5000",
                token="test-token",
                timeout=0,
            )

    @patch("src.infrastructure.backend.backend_http_client.requests.get")
    def test_get_returns_json_object(
        self,
        mock_get: Mock,
    ) -> None:
        """Ensure GET returns a valid JSON object."""

        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "Success",
        }
        mock_get.return_value = mock_response

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        result = client.get("/api/v1/test")

        assert result == {"status": "Success"}

        mock_get.assert_called_once_with(
            "http://localhost:5000/api/v1/test",
            headers={
                "Authorization": "Bearer test-token",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

        mock_response.raise_for_status.assert_called_once()

    @patch("src.infrastructure.backend.backend_http_client.requests.post")
    def test_post_returns_json_object(
        self,
        mock_post: Mock,
    ) -> None:
        """Ensure POST sends JSON and returns a valid response."""

        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "Success",
        }
        mock_post.return_value = mock_response

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        payload = {
            "databaseConfigId": "db-001",
        }

        result = client.post(
            "/api/v1/semantic-layer/upload",
            payload,
        )

        assert result == {"status": "Success"}

        mock_post.assert_called_once_with(
            "http://localhost:5000/api/v1/semantic-layer/upload",
            headers={
                "Authorization": "Bearer test-token",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

        mock_response.raise_for_status.assert_called_once()

    @patch("src.infrastructure.backend.backend_http_client.requests.get")
    def test_get_file_returns_raw_content(
        self,
        mock_get: Mock,
    ) -> None:
        """Ensure file retrieval returns raw response content."""

        file_content = b"sample file content"

        mock_response = Mock()
        mock_response.content = file_content
        mock_get.return_value = mock_response

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        result = client.get_file(
            "/api/v1/semantic-layer/files/file-001"
        )

        assert result == file_content

        mock_get.assert_called_once_with(
            "http://localhost:5000/api/v1/semantic-layer/files/file-001",
            headers={
                "Authorization": "Bearer test-token",
                "Accept": "application/octet-stream",
            },
            timeout=30,
        )

        mock_response.raise_for_status.assert_called_once()

    def test_get_rejects_empty_endpoint(self) -> None:
        """Ensure GET rejects an empty endpoint."""

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        with pytest.raises(
            ValueError,
            match="endpoint cannot be empty",
        ):
            client.get("")

    def test_post_rejects_empty_endpoint(self) -> None:
        """Ensure POST rejects an empty endpoint."""

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        with pytest.raises(
            ValueError,
            match="endpoint cannot be empty",
        ):
            client.post("", {})

    def test_get_file_rejects_empty_endpoint(self) -> None:
        """Ensure file retrieval rejects an empty endpoint."""

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        with pytest.raises(
            ValueError,
            match="endpoint cannot be empty",
        ):
            client.get_file("")

    @patch("src.infrastructure.backend.backend_http_client.requests.get")
    def test_get_raises_http_error(
        self,
        mock_get: Mock,
    ) -> None:
        """Ensure GET propagates Backend HTTP errors."""

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "401 Unauthorized"
        )
        mock_get.return_value = mock_response

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="invalid-token",
        )

        with pytest.raises(requests.HTTPError):
            client.get("/api/v1/test")

    @patch("src.infrastructure.backend.backend_http_client.requests.post")
    def test_post_raises_http_error(
        self,
        mock_post: Mock,
    ) -> None:
        """Ensure POST propagates Backend HTTP errors."""

        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "400 Bad Request"
        )
        mock_post.return_value = mock_response

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        with pytest.raises(requests.HTTPError):
            client.post(
                "/api/v1/test",
                {},
            )

    @patch("src.infrastructure.backend.backend_http_client.requests.get")
    def test_get_rejects_non_object_json_response(
        self,
        mock_get: Mock,
    ) -> None:
        """Ensure GET rejects JSON responses that are not objects."""

        mock_response = Mock()
        mock_response.json.return_value = ["invalid"]
        mock_get.return_value = mock_response

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        with pytest.raises(
            ValueError,
            match="Backend response must be a JSON object",
        ):
            client.get("/api/v1/test")

    @patch("src.infrastructure.backend.backend_http_client.requests.post")
    def test_post_rejects_non_object_json_response(
        self,
        mock_post: Mock,
    ) -> None:
        """Ensure POST rejects JSON responses that are not objects."""

        mock_response = Mock()
        mock_response.json.return_value = ["invalid"]
        mock_post.return_value = mock_response

        client = BackendHttpClient(
            base_url="http://localhost:5000",
            token="test-token",
        )

        with pytest.raises(
            ValueError,
            match="Backend response must be a JSON object",
        ):
            client.post(
                "/api/v1/test",
                {},
            )