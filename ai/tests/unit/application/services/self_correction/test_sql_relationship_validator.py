from src.application.services.self_correction.validators.sql_relationship_validator import (
    SQLRelationshipValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)


_SCHEMA = {
    "tables": {
        "customers": {"columns": [{"name": "customer_id"}]},
        "accounts": {"columns": [{"name": "customer_id"}]},
    },
    "relationships": [
        {
            "name": "customers_accounts",
            "from_table": "customers",
            "from_column": "customer_id",
            "to_table": "accounts",
            "to_column": "customer_id",
        }
    ],
}


class _SchemaProvider:
    def get_schema(self):
        return _SCHEMA


class _LegacySemanticRepository:
    def load(self):
        # Legacy revision with relationship display data only: no join columns.
        return {"relationships": [{"name": "customers_accounts"}]}


def test_uses_explicit_backend_schema_relationship_when_legacy_revision_is_incomplete():
    syntax = SQLSyntaxValidator()
    validator = SQLRelationshipValidator(
        _LegacySemanticRepository(),
        syntax,
        SQLSchemaValidator(_SchemaProvider(), syntax),
    )

    result = validator.validate(
        "SELECT c.customer_id FROM customers c "
        "INNER JOIN accounts a ON c.customer_id = a.customer_id",
        schema=_SCHEMA,
    )

    assert result.is_valid
