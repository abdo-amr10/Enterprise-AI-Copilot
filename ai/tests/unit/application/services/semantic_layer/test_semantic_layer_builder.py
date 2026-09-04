"""Unit tests for the canonical FullRebuildBuilder."""

from unittest.mock import Mock
import json

from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)


class TestFullRebuildBuilder:
    """Tests for the canonical full-rebuild builder."""

    def test_build_generates_initial_draft(self):
        """Build should send the generated prompt to the LLM and return its response."""

        llm_client = Mock()

        expected_text = (
            '{"metadata": {"status": "initial_draft", '
            '"validated": false, "human_review_required": true}, '
            '"entities": [{"mapping": "customers"}]}'
        )

        llm_client.generate.return_value = GenerationResponse(
            text=expected_text
        )

        build_input = SemanticLayerBuildInput(
            schema={
                "version": "1.0",
                "database": "Test Database",
                "tables": {
                    "customers": {
                        "columns": [
                            {
                                "name": "customer_id",
                                "type": "int",
                                "primary_key": True,
                            }
                        ]
                    }
                },
            },
            relationships=[],
            documentation=None,
            business_glossary=None,
            sample_data=None,
        )

        builder = FullRebuildBuilder(llm_client)

        result = builder.build(build_input)
        assert isinstance(result, SemanticLayerBuildResponse)
        assert result.semantic_layer["metadata"]["status"] == "initial_draft"
        assert len(result.semantic_layer["entities"]) >= 1
        assert result.semantic_layer["entities"][0]["mapping"] == "customers"
        llm_client.generate.assert_called_once()

        generation_request = llm_client.generate.call_args.args[0]

        assert "SCHEMA:" in generation_request.prompt
        assert "RELATIONSHIPS:" in generation_request.prompt
        assert "DOCUMENTATION:\nNot provided." in generation_request.prompt
        assert "BUSINESS GLOSSARY:\nNot provided." in generation_request.prompt
        assert "SAMPLE DATA:\nNot provided." in generation_request.prompt

    def test_reconciliation_keeps_only_provided_relationships_and_safe_metadata(self):
        llm_client = Mock()
        llm_client.generate.return_value = GenerationResponse(
            text=json.dumps(
                {
                    "metadata": {"status": "initial_draft"},
                    "entities": [
                        {"name": "Customer", "mapping": "customers", "security_domain": "branch"}
                    ],
                    "relationships": [
                        {"name": "invented", "status": "INFERRED"}
                    ],
                    "measures": [
                        {"name": "Average Credit Score", "mapping": "customers.credit_score", "aggregation": "AVG"},
                        {"name": "Total Amount Usd", "mapping": "transactions.amount_usd", "aggregation": "SUM"},
                        {"name": "Customers Count", "mapping": "customers.customer_id", "aggregation": "COUNT DISTINCT", "distinct_required": True},
                    ],
                    "dimensions": [
                        {"name": "Customers Email", "mapping": "customers.email"},
                        {"name": "Transactions Transaction Date", "mapping": "transactions.transaction_date"},
                    ],
                    "business_rules": [{"name": "`customers", "description": "customers.customer_id -> accounts.customer_id"}],
                }
            )
        )
        schema = {
            "tables": {
                "customers": {"columns": [
                    {"name": "customer_id", "type": "varchar", "primary_key": True},
                    {"name": "email", "type": "varchar", "primary_key": False},
                    {"name": "credit_score", "type": "int", "primary_key": False},
                ]},
                "transactions": {"columns": [
                    {"name": "transaction_id", "type": "varchar", "primary_key": True},
                    {"name": "amount_usd", "type": "decimal", "primary_key": False},
                    {"name": "transaction_date", "type": "datetime", "primary_key": False},
                ]},
            }
        }
        relationships = [
            {"name": "customers_transactions", "from_table": "customers", "from_column": "customer_id", "to_table": "transactions", "to_column": "transaction_id", "status": "INFERRED"},
            {"name": "provided_relationship", "from_table": "customers", "from_column": "customer_id", "to_table": "transactions", "to_column": "transaction_id", "status": "PROVIDED"},
        ]
        result = FullRebuildBuilder(llm_client).build(
            SemanticLayerBuildInput(schema=schema, relationships=relationships)
        ).semantic_layer

        assert [r["name"] for r in result["relationships"]] == ["provided_relationship"]
        assert result["relationships"][0]["status"] == "PROVIDED"
        assert result["entities"][0]["security_domain"] is None
        assert {m["name"] for m in result["measures"]} == {"Customer Count"}
        count = next(m for m in result["measures"] if m["name"] == "Customer Count")
        assert count["aggregation"] == "COUNT"
        assert count["distinct_required"] is False
        dimensions = {d["mapping"]: d for d in result["dimensions"]}
        assert dimensions["customers.email"]["name"] == "Email"
        assert dimensions["customers.email"]["is_pii"] is True
        assert dimensions["transactions.transaction_date"]["type"] == "temporal"
        assert result["business_rules"] == []

    def test_glossary_supplies_derived_measures_and_ambiguity_rules(self):
        glossary = """| Business Term | Database Mapping | Meaning |
|---|---|---|
| Transaction Volume | Derived from `transactions.amount_usd` | Sum of transaction amounts. |

## Ambiguity Rules

- When a user asks for **customer transactions**, join through `accounts`.
"""
        metadata = FullRebuildBuilder._extract_documentation_metadata(None, glossary)
        measures = FullRebuildBuilder._extract_glossary_measures(glossary)

        assert measures[0]["name"] == "Transaction Volume"
        assert measures[0]["mapping"] == "transactions.amount_usd"
        assert measures[0]["aggregation"] == "SUM"
        assert metadata["business_rules"] == [
            {
                "name": "Customer Transactions",
                "description": "When a user asks for **customer transactions**, join through accounts.",
                "source": "business_glossary",
                "generated": False,
                "rule_type": "join_guidance",
                "enforcement": "mandatory",
            }
        ]

    def test_dimension_names_are_disambiguated_only_when_required(self):
        dimensions = [
            {"name": "Customer ID", "mapping": "customers.customer_id"},
            {"name": "Customer ID", "mapping": "accounts.customer_id"},
            {"name": "City", "mapping": "customers.city"},
            {"name": "City", "mapping": "branches.city"},
            {"name": "Card Type", "mapping": "cards.card_type"},
        ]

        FullRebuildBuilder._ensure_unique_dimension_names(dimensions)

        assert [dimension["name"] for dimension in dimensions] == [
            "Customer ID",
            "Account Customer ID",
            "Customer City",
            "Branch City",
            "Card Type",
        ]
