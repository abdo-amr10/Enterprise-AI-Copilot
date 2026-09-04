"""Deterministic preflight validation service.

Acts as a lightweight, deterministic gate before expensive Context Retrieval
and LLM SQL generation. Validates explicit table existence against authoritative
schema metadata.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.application.services.preflight.enums import PreflightAction
from src.application.services.preflight.models import PreflightResult

logger = logging.getLogger(__name__)


class PreflightService:
    """Orchestrates lightweight, deterministic table existence checks before Text-to-SQL generation.

    This service performs no LLM calls, semantic retrieval, join/relationship inference,
    or SQL generation/validation. It checks only whether deterministically identified
    explicit table references exist in the authoritative database schema.
    """

    _STOPWORDS = {
        # Determiners & articles
        "a", "an", "the", "this", "that", "these", "those",
        "each", "every", "all", "any", "some", "few", "more", "most", "no", "nor", "not",
        "my", "our", "your", "his", "her", "its", "their",
        "new", "old", "same", "different", "main", "entire", "whole", "single",
        "first", "last", "next", "previous",
        # Data & SQL concepts
        "database", "data", "db", "schema", "view", "column", "columns", "row", "rows",
        "record", "records", "pivot", "html", "markdown", "summary", "lookup",
        "format", "name", "names", "structure", "type", "types", "empty", "null",
        "result", "results", "info", "information", "value", "values", "metric", "metrics",
        "table", "tables", "details",
        # Prepositions & conjunctions
        "from", "in", "into", "of", "to", "for", "with", "on", "at", "by", "about",
        "as", "and", "or", "but", "if", "then", "else", "so", "than",
        # Verbs & SQL keywords
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "please", "thanks", "thank",
        "show", "get", "select", "list", "find", "give", "display", "fetch", "return",
        "can", "could", "would", "should", "will", "may", "might", "must",
        "join", "inner", "outer", "left", "right", "cross", "full", "natural", "union",
        "where", "having", "group", "order", "limit", "offset", "set",
        "create", "drop", "alter", "insert", "delete", "update", "values",
        # Pronouns & interrogatives
        "which", "what", "where", "how", "who", "whom", "whose", "when", "why",
    }

    _TABLE_PATTERNS = (
        # e.g., "from table customers", "in table 'accounts'", "into table [branches]"
        re.compile(
            r"\b(?:from|in|into|update|join|on)\s+tables?\s+['\"`\[]?([a-zA-Z_][a-zA-Z0-9_]*)['\"`\]]?",
            re.IGNORECASE,
        ),
        # e.g., "table of customers", "tables of accounts"
        re.compile(
            r"\btables?\s+of\s+['\"`\[]?([a-zA-Z_][a-zA-Z0-9_]*)['\"`\]]?",
            re.IGNORECASE,
        ),
        # e.g., "table customers", "tables: customers", "table `orders`"
        re.compile(
            r"\btables?(?:\s*:|\s+)\s*['\"`\[]?([a-zA-Z_][a-zA-Z0-9_]*)['\"`\]]?",
            re.IGNORECASE,
        ),
        # e.g., "customers table", "the accounts table", "[orders] table"
        re.compile(
            r"['\"`\[]?([a-zA-Z_][a-zA-Z0-9_]*)['\"`\]]?\s+tables?\b",
            re.IGNORECASE,
        ),
        # e.g., "FROM customers", "FROM [accounts]", "JOIN orders"
        re.compile(
            r"\b(?:FROM|JOIN)\s+['\"`\[]?([a-zA-Z_][a-zA-Z0-9_]*)['\"`\]]?(?=\s+WHERE|\s+GROUP|\s+ORDER|\s+JOIN|\s+INNER|\s+LEFT|\s+RIGHT|\s+ON|\s*;|\s*$)",
            re.IGNORECASE,
        ),
    )

    def __init__(
        self,
        schema_provider: Any = None,
    ) -> None:
        self._schema_provider = schema_provider
        self._cached_tables: set[str] | None = None

    def _get_known_tables(self) -> set[str]:
        """Retrieve and cache normalized table names from the authoritative schema provider."""
        if self._cached_tables is not None:
            return self._cached_tables

        if self._schema_provider is None:
            raise ValueError("No schema provider configured.")

        tables: set[str] = set()
        if isinstance(self._schema_provider, (set, frozenset, list, tuple)):
            tables = {str(t).casefold() for t in self._schema_provider}
        elif isinstance(self._schema_provider, dict):
            raw_tables = self._schema_provider.get("tables", self._schema_provider)
            if isinstance(raw_tables, dict):
                tables = {str(t).casefold() for t in raw_tables.keys()}
            elif isinstance(raw_tables, (list, set, tuple)):
                tables = {str(t).casefold() for t in raw_tables}
        elif hasattr(self._schema_provider, "get_schema"):
            schema = self._schema_provider.get_schema()
            if isinstance(schema, dict) and isinstance(schema.get("tables"), dict):
                tables = {str(t).casefold() for t in schema["tables"].keys()}
            else:
                raise ValueError("Schema provider returned invalid schema format.")
        else:
            raise ValueError("Unsupported schema provider type.")

        self._cached_tables = tables
        return self._cached_tables

    def extract_table_references(self, question: str) -> list[str]:
        """Extract explicit table references from question if present."""
        cleaned = question.strip() if question else ""
        if not cleaned:
            return []

        found: list[str] = []
        seen: set[str] = set()

        for pattern in self._TABLE_PATTERNS:
            for match in pattern.finditer(cleaned):
                table_name = match.group(1).strip()
                norm = table_name.casefold()
                if norm not in self._STOPWORDS and norm not in seen:
                    seen.add(norm)
                    found.append(table_name)

        return found

    def check(self, question: str) -> PreflightResult:
        """Run deterministic table existence preflight check against the question.

        Args:
            question: The natural-language user question to validate.

        Returns:
            PreflightResult indicating PASS, SKIP, or BLOCK.
        """
        cleaned = question.strip() if question else ""
        if not cleaned:
            return PreflightResult(
                action=PreflightAction.SKIP,
                code="NO_APPLICABLE_TABLE_CHECK",
                message="No applicable table check for an empty question.",
            )

        if self._schema_provider is None:
            return PreflightResult(
                action=PreflightAction.SKIP,
                code="NO_APPLICABLE_TABLE_CHECK",
                message="No schema provider configured.",
            )

        try:
            referenced_tables = self.extract_table_references(cleaned)
            if not referenced_tables:
                return PreflightResult(
                    action=PreflightAction.SKIP,
                    code="NO_APPLICABLE_TABLE_CHECK",
                    message="No explicit table reference detected in question.",
                )

            known_tables = self._get_known_tables()

            # Check if any explicitly referenced table is missing from authoritative schema
            missing_tables = [
                tbl for tbl in referenced_tables if tbl.casefold() not in known_tables
            ]

            if missing_tables:
                first_missing = missing_tables[0]
                return PreflightResult(
                    action=PreflightAction.BLOCK,
                    code="TABLE_NOT_FOUND",
                    message=(
                        f"The referenced table '{first_missing}' was not found "
                        f"in the authoritative database schema."
                    ),
                    metadata={
                        "referenced_table": first_missing,
                        "missing_tables": missing_tables,
                        "entity_type": "table",
                    },
                )

            return PreflightResult(
                action=PreflightAction.PASS,
                code="TABLE_FOUND",
                message="All explicitly referenced tables exist in the authoritative database schema.",
                metadata={
                    "referenced_tables": referenced_tables,
                    "entity_type": "table",
                },
            )

        except Exception as exc:
            logger.warning(
                "Preflight table check encountered an unexpected error and will fail open: %s",
                exc,
            )
            return PreflightResult(
                action=PreflightAction.SKIP,
                code="PREFLIGHT_ERROR",
                message="Preflight check failed open due to an internal error.",
                metadata={"error": str(exc)},
            )
