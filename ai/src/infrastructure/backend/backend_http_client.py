from typing import Any

import requests


class BackendHttpClient:
    """Provides shared HTTP communication with the Backend API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: int = 30,
    ) -> None:
        """Initialize the Backend HTTP client.

        Args:
            base_url: Base URL of the Backend API.
            token: JWT token used for authenticated requests.
            timeout: Maximum time in seconds allowed for a request.

        Raises:
            ValueError: If the base URL or token is empty,
                or if the timeout is not positive.
        """
        if not base_url.strip():
            raise ValueError("base_url cannot be empty.")

        if not token.strip():
            raise ValueError("token cannot be empty.")

        if timeout <= 0:
            raise ValueError("timeout must be greater than zero.")

        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    def get(self, endpoint: str) -> dict[str, Any]:
        """Send an authenticated GET request to the Backend.

        Args:
            endpoint: API endpoint relative to the Backend base URL.

        Returns:
            Parsed JSON response.

        Raises:
            ValueError: If the endpoint is empty or the response
                is not a JSON object.
            requests.HTTPError: If the Backend returns an HTTP error.
        """
        if not endpoint.strip():
            raise ValueError("endpoint cannot be empty.")

        response = requests.get(
            self._build_url(endpoint),
            headers=self._json_headers(),
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Backend response must be a JSON object."
            )

        return data

    def post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send an authenticated POST request to the Backend.

        Args:
            endpoint: API endpoint relative to the Backend base URL.
            payload: JSON request body.

        Returns:
            Parsed JSON response.

        Raises:
            ValueError: If the endpoint is empty or the response
                is not a JSON object.
            requests.HTTPError: If the Backend returns an HTTP error.
        """
        if not endpoint.strip():
            raise ValueError("endpoint cannot be empty.")

        response = requests.post(
            self._build_url(endpoint),
            headers=self._json_headers(),
            json=payload,
            timeout=self._timeout,
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(
                "Backend response must be a JSON object."
            )

        return data

    def get_file(self, endpoint: str) -> bytes:
        """Retrieve raw file content from the Backend.

        Args:
            endpoint: File endpoint relative to the Backend base URL.

        Returns:
            Raw file content.

        Raises:
            ValueError: If the endpoint is empty.
            requests.HTTPError: If the Backend returns an HTTP error.
        """
        if not endpoint.strip():
            raise ValueError("endpoint cannot be empty.")

        response = requests.get(
            self._build_url(endpoint),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/octet-stream",
            },
            timeout=self._timeout,
        )

        response.raise_for_status()

        return response.content

    def _build_url(self, endpoint: str) -> str:
        """Build the complete Backend URL.

        Args:
            endpoint: API endpoint relative to the Backend base URL.

        Returns:
            Complete Backend URL.
        """
        return (
            f"{self._base_url}/{endpoint.lstrip('/')}"
        )

    def _json_headers(self) -> dict[str, str]:
        """Build headers for authenticated JSON requests.

        Returns:
            HTTP headers containing authentication and JSON metadata.
        """
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def put(
        self,
        endpoint: str,
        payload: dict,
    ) -> dict:
            """Send an authenticated PUT request to the Backend.

            Args:
                endpoint: API endpoint relative to the Backend base URL.
                payload: JSON request body.

            Returns:
                Parsed JSON response.

            Raises:
                ValueError: If the endpoint is empty or the response is invalid.
                requests.HTTPError: If the Backend returns an HTTP error.
            """

            if not endpoint.strip():
                raise ValueError("endpoint cannot be empty.")

            response = requests.put(
                f"{self._base_url}/{endpoint.lstrip('/')}",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, dict):
                raise ValueError("Backend response must be a JSON object.")

            return data