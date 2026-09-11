from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)


def test_accepts_a_single_select_statement() -> None:
    result = SQLSyntaxValidator().validate("SELECT customer_id FROM customers")

    assert result.is_valid


def test_rejects_write_statements() -> None:
    result = SQLSyntaxValidator().validate("DELETE FROM customers")

    assert not result.is_valid
    assert result.issues[0].type == "NOT_READ_ONLY"


def test_rejects_write_in_multiple_statements() -> None:
    result = SQLSyntaxValidator().validate("SELECT 1; DROP TABLE customers")

    assert not result.is_valid
    assert result.issues[0].type == "NOT_READ_ONLY"


def test_accepts_multiple_read_only_select_statements() -> None:
    result = SQLSyntaxValidator().validate("SELECT 1; SELECT 2")

    assert result.is_valid
