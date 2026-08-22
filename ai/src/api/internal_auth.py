"""Service-to-service authentication for non-public AI Runtime endpoints."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


def require_internal_service(x_internal_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("AI_INTERNAL_API_KEY")
    if not expected or not x_internal_api_key or not hmac.compare_digest(expected, x_internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal service credentials.")
