"""Optional, explicit checks against local reference data.

The SQL runtime normally has schema metadata only.  For the demo dataset we
also have a bounded, non-authoritative sample-data file.  This service uses it
only to explain a known missing branch-manager value before generating SQL; it
does not infer schema, joins, or business rules from sample rows.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class ReferenceDataPreflight:
    """Detect a requested branch manager that is absent from local reference data."""

    _MANAGER_PATTERNS = (
        re.compile(
        r"\b(?:whose\s+)?manager\s+is\s+['\"]?([\w .'-]+?)['\"]?(?:[?.!]|$)",
        re.IGNORECASE,
        ),
        re.compile(
            r"\bbranch\s+of\s+['\"]?([\w .'-]+?)['\"]?(?:[?.!]|$)",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b([A-Z][\w.-]*(?:\s+[A-Z][\w.-]*)+)\s*'s\s+branch\b",
        ),
    )

    def __init__(self, sample_data_path: str | Path) -> None:
        self._sample_data_path = Path(sample_data_path)

    def check_branch_manager(self, question: str) -> tuple[str, tuple[str, ...]] | None:
        """Return the missing requested name and observed names, if applicable.

        ``None`` means either that the question has no manager filter or the
        value exists in the local reference dataset.
        """
        match = next(
            (pattern.search(question.strip()) for pattern in self._MANAGER_PATTERNS if pattern.search(question.strip())),
            None,
        )
        if match is None:
            return None

        requested = " ".join(match.group(1).split())
        with self._sample_data_path.open(encoding="utf-8") as source:
            sample_data = json.load(source)

        managers = tuple(
            branch["manager_name"]
            for branch in sample_data.get("branches", [])
            if isinstance(branch, dict) and isinstance(branch.get("manager_name"), str)
        )
        if requested.casefold() in {manager.casefold() for manager in managers}:
            return None
        return requested, managers
