from src.application.services.self_correction.validators.sql_schema_validator import SQLSchemaValidator
from src.application.services.self_correction.validators.sql_syntax_validator import SQLSyntaxValidator


class InMemorySchemaProvider:
    def __init__(self, schema: dict) -> None:
        self._schema = schema

    def get_schema(self) -> dict:
        return self._schema


SAMPLE_SCHEMA = {
    "tables": {
        "customers": {
            "columns": [
                {"name": "customer_id", "type": "varchar(20)"},
                {"name": "first_name", "type": "varchar(50)"},
                {"name": "last_name", "type": "varchar(50)"},
                {"name": "email", "type": "varchar(100)"},
                {"name": "credit_score", "type": "int"},
                {"name": "created_at", "type": "datetime"},
            ]
        },
        "transactions": {
            "columns": [
                {"name": "transaction_id", "type": "varchar(20)"},
                {"name": "amount_usd", "type": "decimal(10,2)"},
                {"name": "transaction_date", "type": "datetime"},
            ]
        },
    }
}


def test_rejects_avg_on_varchar_column() -> None:
    validator = SQLSchemaValidator(InMemorySchemaProvider(SAMPLE_SCHEMA), SQLSyntaxValidator())
    result = validator.validate("SELECT AVG(c.first_name) FROM customers AS c")

    assert not result.is_valid
    assert len(result.issues) == 1
    assert result.issues[0].type == "TYPE_MISMATCH"
    assert "Cannot apply aggregation function 'AVG' to non-numeric column 'customers.first_name'" in result.issues[0].message


def test_rejects_sum_on_varchar_column() -> None:
    validator = SQLSchemaValidator(InMemorySchemaProvider(SAMPLE_SCHEMA), SQLSyntaxValidator())
    result = validator.validate("SELECT SUM(c.email) FROM customers AS c")

    assert not result.is_valid
    assert len(result.issues) == 1
    assert result.issues[0].type == "TYPE_MISMATCH"


def test_rejects_avg_on_datetime_column() -> None:
    validator = SQLSchemaValidator(InMemorySchemaProvider(SAMPLE_SCHEMA), SQLSyntaxValidator())
    result = validator.validate("SELECT AVG(c.created_at) FROM customers AS c")

    assert not result.is_valid
    assert result.issues[0].type == "TYPE_MISMATCH"


def test_allows_avg_and_sum_on_numeric_columns() -> None:
    validator = SQLSchemaValidator(InMemorySchemaProvider(SAMPLE_SCHEMA), SQLSyntaxValidator())
    result = validator.validate("SELECT AVG(c.credit_score), SUM(t.amount_usd) FROM customers AS c JOIN transactions AS t ON 1=1")

    assert result.is_valid


def test_allows_count_min_max_on_varchar_and_datetime() -> None:
    validator = SQLSchemaValidator(InMemorySchemaProvider(SAMPLE_SCHEMA), SQLSyntaxValidator())
    result = validator.validate("SELECT COUNT(c.first_name), MIN(c.first_name), MAX(c.created_at) FROM customers AS c")

    assert result.is_valid
