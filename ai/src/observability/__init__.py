"""Developer-only observability and evaluation helpers.

This package is deliberately outside the request-serving API.  Importing it
does not initialise MLflow or alter the production composition root.
"""

from src.observability.latency_audit import (
    request_lifecycle,
    stage as audit_stage,
    record_prompt,
    record_llm_call,
    record_backend_call,
    record_validation,
    record_critic,
    record_correction_attempt,
)
