import time
from typing import Any

import requests


def _safe_record_resp_meta(response: Any, timing_info: dict[str, Any]) -> None:
    try:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            timing_info["status_code"] = status_code
        headers = getattr(response, "headers", None)
        if hasattr(headers, "get"):
            timing_info["backend_request_id"] = headers.get("X-Request-ID") or headers.get("x-request-id")
        content = getattr(response, "content", None)
        if isinstance(content, (bytes, str)):
            timing_info["response_bytes"] = len(content)
    except Exception:
        pass


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
            base_url: Base URL of the Backend API (e.g. http://localhost:5226).
            token: Optional pre-configured Bearer token.
            email: Optional email for auto-login.
            password: Optional password for auto-login.
            timeout: Maximum time in seconds allowed for a request.
            verify_tls: Whether to verify SSL/TLS certificates.

        Raises:
            ValueError: If the base_url is empty, or if neither token nor login
                credentials are provided, or if the timeout is not positive.
        """
        if not base_url.strip():
            raise ValueError("base_url cannot be empty.")
        if not token.strip() and not (email.strip() and password.strip()):
            raise ValueError(
                "Either a Bearer token or email/password credentials must be provided."
            )
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero.")

        self._base_url = base_url.rstrip("/")
        self._token = token
        self._email = email
        self._password = password
        self._timeout = timeout
        self._verify_tls = verify_tls

        if not self._token and self._email and self._password:
            self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with the Backend using email/password to retrieve a JWT token."""
        if not self._email or not self._password:
            return

        login_url = f"{self._base_url}/api/v1/Auth/login"
        t_total_start = time.perf_counter_ns()
        status_code = None
        exc_thrown = None
        client_prep = 0.0
        http_req = 0.0
        resp_proc = 0.0
        try:
            t_prep = time.perf_counter_ns()
            login_headers = {"Accept": "application/json", "Content-Type": "application/json"}
            login_payload = {"email": self._email, "password": self._password}
            tls_opts = self._tls_options()
            client_prep = (time.perf_counter_ns() - t_prep) / 1_000_000.0

            t_http = time.perf_counter_ns()
            response = requests.post(
                login_url,
                headers=login_headers,
                json=login_payload,
                timeout=self._timeout,
                **tls_opts,
            )
            http_req = (time.perf_counter_ns() - t_http) / 1_000_000.0

            t_proc = time.perf_counter_ns()
            status_code = response.status_code
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or "token" not in data:
                raise ValueError("Backend login response did not contain a valid token.")
            self._token = data["token"]
            resp_proc = (time.perf_counter_ns() - t_proc) / 1_000_000.0
        except Exception as exc:
            exc_thrown = exc
            raise
        finally:
            t_total_end = time.perf_counter_ns()
            dur_ms = (t_total_end - t_total_start) / 1_000_000.0
            try:
                from src.observability.latency_audit import record_backend_call
                record_backend_call(
                    stage_name="backend_auth",
                    method="POST",
                    url=login_url,
                    status_code=status_code,
                    duration_ms=dur_ms,
                    timeout=self._timeout,
                    exception=exc_thrown,
                    client_preparation_ms=client_prep,
                    http_request_duration_ms=http_req,
                    response_processing_ms=resp_proc,
                )
            except Exception:
                pass

    def _execute_with_auth_retry(
        self,
        request_fn,
        method: str = "UNKNOWN",
        endpoint: str = "",
        timing_info: dict[str, Any] | None = None,
    ):
        """Execute a request function, retrying once if 401 Unauthorized occurs and credentials exist."""
        t_total_start = time.perf_counter_ns()
        retries = 0
        status_code = None
        req_exc = None
        full_url = self._build_url(endpoint) if endpoint else ""
        try:
            res = request_fn()
            status_code = timing_info.get("status_code", 200) if timing_info else 200
            return res
        except requests.HTTPError as error:
            req_exc = error
            if error.response is not None:
                status_code = error.response.status_code
            if (
                error.response is not None
                and error.response.status_code == 401
                and self._email
                and self._password
            ):
                retries += 1
                try:
                    self._authenticate()
                    res = request_fn()
                    status_code = timing_info.get("status_code", 200) if timing_info else 200
                    req_exc = None
                    return res
                except requests.HTTPError as retry_err:
                    req_exc = retry_err
                    if retry_err.response is not None:
                        status_code = retry_err.response.status_code
                    raise
            raise
        except Exception as exc:
            req_exc = exc
            raise
        finally:
            t_total_end = time.perf_counter_ns()
            backend_total_duration_ms = (t_total_end - t_total_start) / 1_000_000.0
            try:
                from src.observability.latency_audit import record_backend_call
                from src.observability.audit_context import get_current_audit

                ctx = get_current_audit()
                current_stage = (
                    ctx.span_stack[-1][0]
                    if (ctx and ctx.span_stack)
                    else (ctx.final_stage if ctx else "backend_call")
                )
                client_prep = timing_info.get("client_preparation_ms", 0.0) if timing_info else 0.0
                http_req = timing_info.get("http_request_duration_ms", 0.0) if timing_info else 0.0
                resp_proc = timing_info.get("response_processing_ms", 0.0) if timing_info else 0.0
                b_req_id = timing_info.get("backend_request_id") if timing_info else None
                req_b = timing_info.get("request_bytes", 0) if timing_info else 0
                resp_b = timing_info.get("response_bytes", 0) if timing_info else 0
                p_req_id = ctx.request_id if ctx else None

                record_backend_call(
                    stage_name=current_stage,
                    method=method,
                    url=full_url or endpoint,
                    status_code=status_code or (timing_info.get("status_code") if timing_info else None),
                    duration_ms=backend_total_duration_ms,
                    request_bytes=req_b,
                    response_bytes=resp_b,
                    timeout=self._timeout,
                    retry_count=retries,
                    exception=req_exc,
                    client_preparation_ms=client_prep,
                    http_request_duration_ms=http_req,
                    response_processing_ms=resp_proc,
                    backend_request_id=b_req_id,
                    parent_request_id=p_req_id,
                )
            except Exception:
                pass

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

        timing_info: dict[str, Any] = {
            "client_preparation_ms": 0.0,
            "http_request_duration_ms": 0.0,
            "response_processing_ms": 0.0,
            "status_code": None,
            "request_bytes": 0,
            "response_bytes": 0,
            "backend_request_id": None,
        }

        def _do_get():
            t_prep = time.perf_counter_ns()
            url = self._build_url(endpoint)
            headers = self._json_headers()
            tls_opts = self._tls_options()
            timing_info["client_preparation_ms"] = (time.perf_counter_ns() - t_prep) / 1_000_000.0

            t_http = time.perf_counter_ns()
            response = requests.get(
                url,
                headers=headers,
                timeout=self._timeout,
                **tls_opts,
            )
            timing_info["http_request_duration_ms"] = (time.perf_counter_ns() - t_http) / 1_000_000.0

            t_proc = time.perf_counter_ns()
            _safe_record_resp_meta(response, timing_info)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Backend response must be a JSON object.")
            timing_info["response_processing_ms"] = (time.perf_counter_ns() - t_proc) / 1_000_000.0
            return data

        return self._execute_with_auth_retry(_do_get, method="GET", endpoint=endpoint, timing_info=timing_info)

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

        timing_info: dict[str, Any] = {
            "client_preparation_ms": 0.0,
            "http_request_duration_ms": 0.0,
            "response_processing_ms": 0.0,
            "status_code": None,
            "request_bytes": 0,
            "response_bytes": 0,
            "backend_request_id": None,
        }

        def _do_post():
            t_prep = time.perf_counter_ns()
            url = self._build_url(endpoint)
            headers = self._json_headers()
            tls_opts = self._tls_options()
            import json as _json
            try:
                timing_info["request_bytes"] = len(_json.dumps(payload).encode("utf-8"))
            except Exception:
                pass
            timing_info["client_preparation_ms"] = (time.perf_counter_ns() - t_prep) / 1_000_000.0

            t_http = time.perf_counter_ns()
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
                **tls_opts,
            )
            timing_info["http_request_duration_ms"] = (time.perf_counter_ns() - t_http) / 1_000_000.0

            t_proc = time.perf_counter_ns()
            _safe_record_resp_meta(response, timing_info)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Backend response must be a JSON object.")
            timing_info["response_processing_ms"] = (time.perf_counter_ns() - t_proc) / 1_000_000.0
            return data

        return self._execute_with_auth_retry(_do_post, method="POST", endpoint=endpoint, timing_info=timing_info)

    def post_multipart(self, endpoint: str, data: dict[str, str], files: dict[str, Any]) -> dict[str, Any]:
        """Send authenticated multipart form data for optional future backend use."""
        if not endpoint.strip():
            raise ValueError("endpoint cannot be empty.")

        timing_info: dict[str, Any] = {
            "client_preparation_ms": 0.0,
            "http_request_duration_ms": 0.0,
            "response_processing_ms": 0.0,
            "status_code": None,
            "request_bytes": 0,
            "response_bytes": 0,
            "backend_request_id": None,
        }

        def _do_multipart():
            t_prep = time.perf_counter_ns()
            url = self._build_url(endpoint)
            headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
            tls_opts = self._tls_options()
            timing_info["client_preparation_ms"] = (time.perf_counter_ns() - t_prep) / 1_000_000.0

            t_http = time.perf_counter_ns()
            response = requests.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=self._timeout,
                **tls_opts,
            )
            timing_info["http_request_duration_ms"] = (time.perf_counter_ns() - t_http) / 1_000_000.0

            t_proc = time.perf_counter_ns()
            _safe_record_resp_meta(response, timing_info)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Backend response must be a JSON object.")
            timing_info["response_processing_ms"] = (time.perf_counter_ns() - t_proc) / 1_000_000.0
            return payload

        return self._execute_with_auth_retry(_do_multipart, method="POST", endpoint=endpoint, timing_info=timing_info)

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

        timing_info: dict[str, Any] = {
            "client_preparation_ms": 0.0,
            "http_request_duration_ms": 0.0,
            "response_processing_ms": 0.0,
            "status_code": None,
            "request_bytes": 0,
            "response_bytes": 0,
            "backend_request_id": None,
        }

        def _do_get_file():
            t_prep = time.perf_counter_ns()
            url = self._build_url(endpoint)
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/octet-stream",
            }
            tls_opts = self._tls_options()
            timing_info["client_preparation_ms"] = (time.perf_counter_ns() - t_prep) / 1_000_000.0

            t_http = time.perf_counter_ns()
            response = requests.get(
                url,
                headers=headers,
                timeout=self._timeout,
                **tls_opts,
            )
            timing_info["http_request_duration_ms"] = (time.perf_counter_ns() - t_http) / 1_000_000.0

            t_proc = time.perf_counter_ns()
            _safe_record_resp_meta(response, timing_info)
            response.raise_for_status()
            content = response.content
            timing_info["response_processing_ms"] = (time.perf_counter_ns() - t_proc) / 1_000_000.0
            return content

        return self._execute_with_auth_retry(_do_get_file, method="GET", endpoint=endpoint, timing_info=timing_info)

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

        timing_info: dict[str, Any] = {
            "client_preparation_ms": 0.0,
            "http_request_duration_ms": 0.0,
            "response_processing_ms": 0.0,
            "status_code": None,
            "request_bytes": 0,
            "response_bytes": 0,
            "backend_request_id": None,
        }

        def _do_put():
            t_prep = time.perf_counter_ns()
            url = f"{self._base_url}/{endpoint.lstrip('/')}"
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            tls_opts = self._tls_options()
            import json as _json
            try:
                timing_info["request_bytes"] = len(_json.dumps(payload).encode("utf-8"))
            except Exception:
                pass
            timing_info["client_preparation_ms"] = (time.perf_counter_ns() - t_prep) / 1_000_000.0

            t_http = time.perf_counter_ns()
            response = requests.put(
                url,
                headers=headers,
                json=payload,
                timeout=self._timeout,
                **tls_opts,
            )
            timing_info["http_request_duration_ms"] = (time.perf_counter_ns() - t_http) / 1_000_000.0

            t_proc = time.perf_counter_ns()
            _safe_record_resp_meta(response, timing_info)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Backend response must be a JSON object.")
            timing_info["response_processing_ms"] = (time.perf_counter_ns() - t_proc) / 1_000_000.0
            return data

        return self._execute_with_auth_retry(_do_put, method="PUT", endpoint=endpoint, timing_info=timing_info)
