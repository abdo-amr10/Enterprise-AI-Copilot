"""Fixture data for the semantic-layer integration test.

SCHEMA is what SchemaRepository.load() would return in production --
here it doubles as the authoritative schema the Backend attaches to
the 2.1 upload payload and passes to the validator.
"""

import json

SCHEMA = {
    "tables": {
        "Customers": {
            "columns": [
                {"name": "CustomerId", "type": "int"},
                {"name": "Name", "type": "varchar"},
                {"name": "Status", "type": "int"},
            ]
        },
        "Sales": {
            "columns": [
                {"name": "SaleId", "type": "int"},
                {"name": "CustomerId", "type": "int"},
                {"name": "Amount", "type": "decimal"},
                {"name": "SaleDate", "type": "datetime"},
            ]
        },
    },
    "relationships": [
        {
            "name": "Sales_Customers",
            "from_table": "Sales",
            "from_column": "CustomerId",
            "to_table": "Customers",
            "to_column": "CustomerId",
            "cardinality": "many_to_one",
            "relationship_type": "foreign_key",
        }
    ],
}

DOCUMENTATION = "ERP sales/customer subject area used by the Copilot demo."
GLOSSARY = "Active customer: Status = 1."
SAMPLE_DATA = {
    "Customers": [{"CustomerId": 1, "Name": "Acme Co", "Status": 1}],
    "Sales": [{"SaleId": 10, "CustomerId": 1, "Amount": 500.0, "SaleDate": "2026-08-01"}],
}

# ---------------------------------------------------------------------------
# Scenario A: FullRebuild -- canned LLM output that already satisfies the
# validator on the first attempt (no auto-fix round needed).
# ---------------------------------------------------------------------------

FULL_REBUILD_DRAFT = {
    "entities": [
        {"name": "Customer", "mapping": "Customers", "description": "A customer account."},
        {"name": "Sale", "mapping": "Sales", "description": "A single sales transaction."},
    ],
    "relationships": [
        {
            "name": "Sales_Customers",
            "from_table": "Sales",
            "from_column": "CustomerId",
            "to_table": "Customers",
            "to_column": "CustomerId",
            "cardinality": "many_to_one",
            "relationship_type": "foreign_key",
        }
    ],
    "measures": [
        {
            "name": "TotalRevenue",
            "mapping": "Sales.Amount",
            "aggregation": "sum",
            "description": "Sum of sale amounts.",
        }
    ],
    "dimensions": [
        {
            "name": "CustomerStatus",
            "mapping": "Customers.Status",
            "description": "Active/inactive status of a customer.",
        }
    ],
    "business_rules": [
        {
            "name": "ActiveCustomers",
            "description": "Active customers have Status = 1.",
        }
    ],
    "validation_issues": [],
}

FULL_REBUILD_DRAFT_TEXT = json.dumps(FULL_REBUILD_DRAFT, indent=2)

# ---------------------------------------------------------------------------
# Scenario B: Incremental -- regenerates only the two affected objects.
# ---------------------------------------------------------------------------

INCREMENTAL_DRAFT = {
    # NOTE: SemanticLayerMergeService._validate_layer requires a
    # "metadata" key on BOTH approved_layer and incremental_layer, even
    # though SemanticLayerBuildResponse is documented as identity-free
    # ("Identity fields ... are assigned later ... not by the
    # strategy/builder"). Without this empty placeholder, merge()
    # raises "incremental_layer must contain a metadata section" and
    # the Incremental path can never succeed as currently written.
    # Flagged as a real bug found by this test -- see the summary.
    "metadata": {},
    "measures": [
        {
            "name": "AverageOrderValue",
            "mapping": "Sales.Amount",
            "aggregation": "avg",
            "description": "Average sale amount per transaction.",
        }
    ],
    "business_rules": [
        {
            "name": "ActiveCustomers",
            "description": (
                "Active customers have Status = 1 and have placed "
                "at least one order."
            ),
        }
    ],
}

INCREMENTAL_DRAFT_TEXT = json.dumps(INCREMENTAL_DRAFT, indent=2)

# ---------------------------------------------------------------------------
# Scenario C: FullRebuild deliberately broken (unknown column mapping),
# followed by an auto-fixer response that corrects it. Demonstrates the
# validation -> auto-fix retry loop.
# ---------------------------------------------------------------------------

BROKEN_DRAFT = json.loads(json.dumps(FULL_REBUILD_DRAFT))
BROKEN_DRAFT["measures"][0]["mapping"] = "Sales.TotalAmount"  # column doesn't exist

BROKEN_DRAFT_TEXT = json.dumps(BROKEN_DRAFT, indent=2)

# NOTE: the auto-fixer's `_preserve_identity` only copies
# semantic_layer_id / revision_id / base_revision_id back onto the
# corrected draft's metadata -- it does NOT preserve `status`. If the
# "corrected" LLM output omits metadata.status entirely, the very next
# validation pass fails again on `_check_metadata` (missing `status`),
# which would spin the auto-fix loop pointlessly. A real corrected
# response would echo the metadata block it was shown, status
# included, so the canned fixture does the same here.
FIXED_DRAFT_WITH_METADATA = json.loads(json.dumps(FULL_REBUILD_DRAFT))
FIXED_DRAFT_WITH_METADATA["metadata"] = {"status": "initial_draft"}
FIXED_DRAFT_TEXT = json.dumps(FIXED_DRAFT_WITH_METADATA, indent=2)
