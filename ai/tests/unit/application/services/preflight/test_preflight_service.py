"""Unit tests for deterministic PreflightService table existence checks."""

from unittest.mock import Mock

import pytest

from src.application.services.preflight.enums import PreflightAction
from src.application.services.preflight.preflight_service import PreflightService


class MockSchemaProvider:
    def __init__(self, tables: dict[str, dict] | None = None) -> None:
        self._tables = (
            tables
            if tables is not None
            else {
                "customers": {},
                "accounts": {},
                "branches": {},
                "transactions": {},
                "loans": {},
            }
        )

    def get_schema(self) -> dict:
        return {"tables": self._tables}


def test_preflight_skips_when_no_schema_provider_configured() -> None:
    service = PreflightService(schema_provider=None)
    result = service.check("Show accounts from table customers")

    assert result.action == PreflightAction.SKIP
    assert result.code == "NO_APPLICABLE_TABLE_CHECK"


def test_preflight_skips_when_question_is_empty_or_whitespace() -> None:
    service = PreflightService(schema_provider=MockSchemaProvider())
    for empty in ("", "   ", "\t\n"):
        result = service.check(empty)
        assert result.action == PreflightAction.SKIP
        assert result.code == "NO_APPLICABLE_TABLE_CHECK"


def test_preflight_skips_when_no_explicit_table_reference() -> None:
    service = PreflightService(schema_provider=MockSchemaProvider())
    result = service.check("Show all active customers with their account balance")

    assert result.action == PreflightAction.SKIP
    assert result.code == "NO_APPLICABLE_TABLE_CHECK"


def test_preflight_passes_when_explicit_table_exists() -> None:
    service = PreflightService(schema_provider=MockSchemaProvider())
    result = service.check("Show all records from table customers")

    assert result.action == PreflightAction.PASS
    assert result.code == "TABLE_FOUND"
    assert "customers" in result.metadata["referenced_tables"]
    assert result.metadata["entity_type"] == "table"


@pytest.mark.parametrize(
    "question,expected_table",
    [
        ("show all from table customers", "customers"),
        ("select details in table accounts", "accounts"),
        ("show the branches table please", "branches"),
        ("table: transactions", "transactions"),
        ("table of loans", "loans"),
        ("SELECT * FROM customers WHERE balance > 0", "customers"),
        ("JOIN loans ON loans.account_id = accounts.id", "loans"),
    ],
)
def test_preflight_detects_various_explicit_table_syntaxes(
    question: str, expected_table: str
) -> None:
    service = PreflightService(schema_provider=MockSchemaProvider())
    result = service.check(question)

    assert result.action == PreflightAction.PASS
    assert result.code == "TABLE_FOUND"
    assert any(
        t.casefold() == expected_table.casefold()
        for t in result.metadata["referenced_tables"]
    )


def test_preflight_matches_tables_case_insensitively() -> None:
    service = PreflightService(
        schema_provider={"tables": {"CUSTOMERS": {}, "Accounts": {}}}
    )

    for variant in (
        "show data from table customers",
        "show data from table CUSTOMERS",
        "show data from table Customers",
    ):
        result = service.check(variant)
        assert result.action == PreflightAction.PASS
        assert result.code == "TABLE_FOUND"


def test_preflight_ignores_common_stopwords() -> None:
    service = PreflightService(schema_provider=MockSchemaProvider())

    # Stopwords like 'pivot', 'results', 'data', 'summary', etc. should not be treated as table names
    for phrase in (
        "show me a pivot table",
        "format the results in a table",
        "show a table of summary",
        "export the table format",
    ):
        result = service.check(phrase)
        assert result.action == PreflightAction.SKIP
        assert result.code == "NO_APPLICABLE_TABLE_CHECK"


def test_preflight_blocks_when_explicit_table_does_not_exist() -> None:
    service = PreflightService(schema_provider=MockSchemaProvider())
    result = service.check("show data from table non_existent_table")

    assert result.action == PreflightAction.BLOCK
    assert result.code == "TABLE_NOT_FOUND"
    assert "non_existent_table" in result.message
    assert result.metadata["referenced_table"] == "non_existent_table"
    assert result.metadata["entity_type"] == "table"


def test_preflight_blocks_if_any_explicit_table_is_missing() -> None:
    service = PreflightService(schema_provider=MockSchemaProvider())
    result = service.check("join table customers with table fake_orders")

    assert result.action == PreflightAction.BLOCK
    assert result.code == "TABLE_NOT_FOUND"
    assert result.metadata["referenced_table"] == "fake_orders"


def test_preflight_works_with_collection_schema_provider() -> None:
    service = PreflightService(schema_provider={"customers", "accounts"})
    assert service.check("from table customers").action == PreflightAction.PASS
    assert service.check("from table missing").action == PreflightAction.BLOCK


def test_preflight_fails_open_when_schema_provider_raises_exception() -> None:
    failing_provider = Mock()
    failing_provider.get_schema.side_effect = RuntimeError(
        "Database connection timed out"
    )

    service = PreflightService(schema_provider=failing_provider)
    result = service.check("select from table customers")

    assert result.action == PreflightAction.SKIP
    assert result.code == "PREFLIGHT_ERROR"
    assert "Database connection timed out" in result.metadata["error"]


def test_preflight_fails_open_when_schema_structure_is_malformed() -> None:
    malformed_provider = Mock()
    malformed_provider.get_schema.return_value = {"invalid": 123}

    service = PreflightService(schema_provider=malformed_provider)
    result = service.check("select from table customers")

    assert result.action == PreflightAction.SKIP
    assert result.code == "PREFLIGHT_ERROR"
