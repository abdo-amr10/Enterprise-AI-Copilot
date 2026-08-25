import ssl
from urllib.error import HTTPError, URLError

from src.observability.local_diagnostics import backend_request_diagnostic
from src.observability.sanitization import safe_event


def http(status: int):
    return backend_request_diagnostic(HTTPError("https://host", status, "Bearer secret", {}, None))


def test_http_categories_are_truthful() -> None:
    assert http(401)["category"] == "authentication_authorization"
    assert http(403)["category"] == "authentication_authorization"
    assert http(404)["category"] == "endpoint_not_found"
    assert http(500)["category"] == "server_error"


def test_network_categories_are_truthful() -> None:
    assert backend_request_diagnostic(TimeoutError("late"))["category"] == "timeout"
    assert backend_request_diagnostic(URLError(ConnectionRefusedError("refused")))["category"] == "connection_failure"
    assert backend_request_diagnostic(URLError(ssl.SSLError("CERTIFICATE_VERIFY_FAILED")))["category"] == "tls_certificate_failure"
    assert backend_request_diagnostic(ValueError("unknown"))["category"] == "unknown"


def test_diagnostic_never_exposes_tokens_or_headers_and_mlflow_sanitizer_drops_exception() -> None:
    diagnostic = backend_request_diagnostic(HTTPError("https://host", 401, "Bearer abc.def.ghi", {}, None))
    assert "abc.def.ghi" not in str(diagnostic)
    safe = safe_event({"exception": "Bearer abc.def.ghi", "response_message": diagnostic["response_message"]})
    assert "exception" not in safe and "abc.def.ghi" not in str(safe)
