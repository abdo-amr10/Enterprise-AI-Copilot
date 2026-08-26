from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)


class _Schema:
    def get_schema(self):
        return {
            "tables": {
                "customers": {
                    "columns": [
                        {"name": "customer_id"},
                        {"name": "customer_name"},
                    ]
                },
                "accounts": {
                    "columns": [
                        {"name": "customer_id"},
                        {"name": "account_id"},
                    ]
                },
            }
        }


def _validator() -> SQLSchemaValidator:
    syntax = SQLSyntaxValidator()
    return SQLSchemaValidator(_Schema(), syntax)


def test_qualifies_only_an_ambiguous_base_table_projection() -> None:
    sql = (
        "SELECT customer_id "
        "FROM customers c INNER JOIN accounts a "
        "ON c.customer_id = a.customer_id"
    )

    qualified = _validator().qualify_base_table_projection_ambiguities(sql)

    assert "SELECT c.customer_id" in qualified
    assert "ON c.customer_id = a.customer_id" in qualified
    assert _validator().validate(qualified).is_valid


def test_does_not_guess_ambiguous_predicate_or_join_columns() -> None:
    sql = (
        "SELECT c.customer_name "
        "FROM customers c INNER JOIN accounts a "
        "ON customer_id = a.customer_id"
    )

    qualified = _validator().qualify_base_table_projection_ambiguities(sql)

    assert "ON customer_id = a.customer_id" in qualified
    assert not _validator().validate(qualified).is_valid
