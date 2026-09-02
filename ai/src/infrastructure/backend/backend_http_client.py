from typing import Any

import requests


class BackendHttpClient:
    """Provides shared HTTP communication with the Backend API."""

    def __init__(
        self,
        base_url: str,
        token: str = "",
        email: str = "",
        password: str = "",
        timeout: int = 30,
        verify_tls: bool = True,
    ) -> None:
        """Initialize the Backend HTTP client.

        Args:
            base_url: Base URL of the Backend API.
            token: JWT token used for authenticated requests (optional if email/password given).
            email: Service account email for auto-login.
            password: Service account password for auto-login.
            timeout: Maximum time in seconds allowed for a request.
            verify_tls: Whether to verify TLS certificates.

        Raises:
            ValueError: If the base URL is empty, or if neither token nor
                credentials are provided, or if the timeout is not positive.
        """
        if not base_url.strip():
            raise ValueError("base_url cannot be empty.")

        if not token.strip() and not (email.strip() and password.strip()):
            raise ValueError("Either token or (email and password) must be provided.")

        if timeout <= 0:
            raise ValueError("timeout must be greater than zero.")

        self._base_url = base_url.rstrip("/")
        self._token = token.strip()
        self._email = email.strip()
        self._password = password.strip()
        self._timeout = timeout
        self._verify_tls = verify_tls

        if not self._token and self._email and self._password:
            self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with the Backend using email/password to retrieve a JWT token."""
        if not self._email or not self._password:
            return

        login_url = f"{self._base_url}/api/v1/Auth/login"
        response = requests.post(
            login_url,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"email": self._email, "password": self._password},
            timeout=self._timeout,
            **self._tls_options(),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or "token" not in data:
            raise ValueError("Backend login response did not contain a valid token.")
        self._token = data["token"]

    def _execute_with_auth_retry(self, request_fn):
        """Execute a request function, retrying once if 401 Unauthorized occurs and credentials exist."""
        try:
            return request_fn()
        except requests.HTTPError as error:
            if (
                error.response is not None
                and error.response.status_code == 401
                and self._email
                and self._password
            ):
                self._authenticate()
                return request_fn()
            raise

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

        def _do_get():
            response = requests.get(
                self._build_url(endpoint),
                headers=self._json_headers(),
                timeout=self._timeout,
                **self._tls_options(),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Backend response must be a JSON object.")
            return data

        return self._execute_with_auth_retry(_do_get)

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

        def _do_post():
            response = requests.post(
                self._build_url(endpoint),
                headers=self._json_headers(),
                json=payload,
                timeout=self._timeout,
                **self._tls_options(),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Backend response must be a JSON object.")
            return data

        return self._execute_with_auth_retry(_do_post)

    def post_multipart(self, endpoint: str, data: dict[str, str], files: dict[str, Any]) -> dict[str, Any]:
        """Send authenticated multipart form data for optional future backend use."""
        if not endpoint.strip():
            raise ValueError("endpoint cannot be empty.")

        def _do_multipart():
            response = requests.post(
                self._build_url(endpoint),
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
                data=data,
                files=files,
                timeout=self._timeout,
                **self._tls_options(),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Backend response must be a JSON object.")
            return payload

        return self._execute_with_auth_retry(_do_multipart)

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

        def _do_get_file():
            response = requests.get(
                self._build_url(endpoint),
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/octet-stream",
                },
                timeout=self._timeout,
                **self._tls_options(),
            )
            response.raise_for_status()
            return response.content

        return self._execute_with_auth_retry(_do_get_file)

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

    def _tls_options(self) -> dict[str, bool]:
        """Keep normal requests verified; opt out only when explicitly set."""
        return {} if self._verify_tls else {"verify": False}

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

        def _do_put():
            response = requests.put(
                f"{self._base_url}/{endpoint.lstrip('/')}",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
                **self._tls_options(),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Backend response must be a JSON object.")
            return data

        return self._execute_with_auth_retry(_do_put)
