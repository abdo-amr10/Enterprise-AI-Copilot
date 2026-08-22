"""Artifact helpers for live integration tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


TEST_DIRECTORY = Path(__file__).resolve().parent


def repository_root() -> Path:
    for candidate in (TEST_DIRECTORY, *TEST_DIRECTORY.parents):
        if (candidate / "ai").is_dir() and (candidate / "docs" / "database_metadata").is_dir():
            return candidate
    raise RuntimeError("Unable to locate the repository root from the live test directory.")


REPOSITORY_ROOT = repository_root()


@pytest.fixture
def artifact_dir(request: pytest.FixtureRequest) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = TEST_DIRECTORY / "outputs" / request.node.name / timestamp
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def save_json(directory: Path, filename: str, value: Any) -> Path:
    path = directory / filename
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path
