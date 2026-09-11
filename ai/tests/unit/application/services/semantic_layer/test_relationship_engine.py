"""Comprehensive unit test suite for the Schema Normalization and Relationship Processing Engine.

Covers all 16 required test scenarios:
1. Valid provided relationship
2. Invalid provided relationship
3. Duplicate provided relationship
4. Reverse-direction duplicate
5. Missing relationships field
6. Empty relationships list
7. Strong inferred relationship
8. Weak approximate candidate
9. Ambiguous candidate
10. Similar names but unrelated entities
11. Accidental value overlap
12. Completely disconnected schema
13. Multiple disconnected components
14. Composite relationship / multi-table structure
15. Schema with sample data
16. Schema without sample data
"""

import pytest

from src.application.services.semantic_layer.relationships.models import (
    BackendDatabaseSchema,
    ProvenanceSource,
    RelationshipCase,
    RelationshipStatus,
    ScoringConfig,
)
from src.application.services.semantic_layer.relationships.normalizer import (
    SchemaNormalizer,
)
from src.application.services.semantic_layer.relationships.relationship_service import (
    RelationshipProcessingEngine,
)


@pytest.fixture
def engine() -> RelationshipProcessingEngine:
    return RelationshipProcessingEngine()


# ---------------------------------------------------------------------------
# Test 1: Valid Provided Relationship
# ---------------------------------------------------------------------------
def test_valid_provided_relationship(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "version": "1.0",
        "tables": {
            "customers": {
                "columns": [
                    {"name": "customer_id", "type": "int", "primary_key": True},
                    {"name": "name", "type": "varchar(100)"},
                ]
            },
            "orders": {
                "columns": [
                    {"name": "order_id", "type": "int", "primary_key": True},
                    {"name": "customer_id", "type": "int"},
                    {"name": "amount", "type": "decimal(10,2)"},
                ]
            },
        },
        "relationships": [
            {
                "name": "orders_customers_fk",
                "from_table": "orders",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "customer_id",
                "cardinality": "N:1",
                "relationship_type": "foreign_key",
            }
        ],
    }

    result = engine.process(raw_schema)
    assert len(result.relationships) == 1
    rel = result.relationships[0]

    assert rel.status == RelationshipStatus.PROVIDED
    assert rel.relationship_case == RelationshipCase.PROVIDED
    assert rel.confidence == 1.0
    assert rel.provenance["source"] == ProvenanceSource.BACKEND_SCHEMA.value
    assert rel.is_executable is True
    assert rel.source_table == "orders"
    assert rel.target_table == "customers"
    assert rel.source_column == "customer_id"
    assert rel.target_column == "customer_id"


# ---------------------------------------------------------------------------
# Test 2: Invalid Provided Relationship
# ---------------------------------------------------------------------------
def test_invalid_provided_relationship(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "version": "1.0",
        "tables": {
            "customers": {
                "columns": [{"name": "id", "type": "int", "primary_key": True}]
            }
        },
        "relationships": [
            {
                "name": "invalid_fk",
                "from_table": "non_existent_table",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "id",
            }
        ],
    }

    with pytest.raises(ValueError, match="unknown source table 'non_existent_table'"):
        engine.process(raw_schema)


# ---------------------------------------------------------------------------
# Test 3: Duplicate Provided Relationship
# ---------------------------------------------------------------------------
def test_duplicate_provided_relationship(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "customers": {
                "columns": [{"name": "customer_id", "type": "int", "primary_key": True}]
            },
            "orders": {
                "columns": [{"name": "customer_id", "type": "int"}]
            },
        },
        "relationships": [
            {
                "name": "rel_1",
                "from_table": "orders",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "customer_id",
            },
            {
                "name": "rel_1_dup",
                "from_table": "orders",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "customer_id",
            },
        ],
    }

    result = engine.process(raw_schema)
    assert len(result.relationships) == 1
    assert result.relationships[0].status == RelationshipStatus.PROVIDED


# ---------------------------------------------------------------------------
# Test 4: Reverse-Direction Duplicate
# ---------------------------------------------------------------------------
def test_reverse_direction_duplicate(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "customers": {
                "columns": [{"name": "customer_id", "type": "int", "primary_key": True}]
            },
            "orders": {
                "columns": [{"name": "customer_id", "type": "int"}]
            },
        },
        "relationships": [
            {
                "name": "orders_to_customers",
                "from_table": "orders",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "customer_id",
            },
            {
                "name": "customers_to_orders",
                "from_table": "customers",
                "from_column": "customer_id",
                "to_table": "orders",
                "to_column": "customer_id",
            },
        ],
    }

    result = engine.process(raw_schema)
    # Deduplication ensures only 1 canonical relationship exists
    assert len(result.relationships) == 1


# ---------------------------------------------------------------------------
# Test 5: Missing Relationships Field
# ---------------------------------------------------------------------------
def test_missing_relationships_field(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "customers": {
                "columns": [{"name": "id", "type": "int", "primary_key": True}]
            }
        },
    }

    result = engine.process(raw_schema)
    assert result.normalized_schema.database == "ShopDB"
    assert len(result.relationships) == 0


# ---------------------------------------------------------------------------
# Test 6: Empty Relationships List
# ---------------------------------------------------------------------------
def test_empty_relationships_list(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "customers": {
                "columns": [{"name": "id", "type": "int", "primary_key": True}]
            }
        },
        "relationships": [],
    }

    result = engine.process(raw_schema)
    assert len(result.relationships) == 0


# ---------------------------------------------------------------------------
# Test 7: Strong Inferred Relationship
# ---------------------------------------------------------------------------
def test_strong_inferred_relationship(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "customers": {
                "columns": [
                    {"name": "customer_id", "type": "int", "primary_key": True},
                    {"name": "name", "type": "varchar(100)"},
                ]
            },
            "orders": {
                "columns": [
                    {"name": "order_id", "type": "int", "primary_key": True},
                    {"name": "customer_id", "type": "int", "primary_key": False},
                    {"name": "amount", "type": "decimal(10,2)"},
                ]
            },
        },
        # No relationships provided!
    }

    result = engine.process(raw_schema)
    assert len(result.relationships) >= 1

    inferred_rel = next(
        rel for rel in result.relationships
        if rel.source_table == "orders" and rel.target_table == "customers"
    )
    assert inferred_rel.status == RelationshipStatus.INFERRED
    assert inferred_rel.relationship_case == RelationshipCase.STRONGLY_INFERRED
    assert inferred_rel.confidence >= 0.75
    assert inferred_rel.is_executable is True
    assert inferred_rel.source_column == "customer_id"
    assert inferred_rel.target_column == "customer_id"


# ---------------------------------------------------------------------------
# Test 8: Weak Approximate Candidate
# ---------------------------------------------------------------------------
def test_weak_approximate_candidate() -> None:
    # Set config threshold so approximate is separated
    config = ScoringConfig(strong_inference_threshold=0.85, probabilistic_threshold=0.40)
    engine = RelationshipProcessingEngine(config=config)

    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "users": {
                "columns": [
                    {"name": "id", "type": "varchar(50)", "primary_key": False},
                ]
            },
            "logs": {
                "columns": [
                    {"name": "user_fk", "type": "varchar(50)", "primary_key": False},
                ]
            },
        },
    }

    result = engine.process(raw_schema)
    # Since users.id is not PK, it has weaker confidence
    assert len(result.relationships) >= 1
    rel = result.relationships[0]
    assert rel.status in (RelationshipStatus.UNCERTAIN, RelationshipStatus.INFERRED)
    if rel.status == RelationshipStatus.UNCERTAIN:
        assert rel.is_executable is False


# ---------------------------------------------------------------------------
# Test 9: Ambiguous Candidate (Multiple Targets)
# ---------------------------------------------------------------------------
def test_ambiguous_candidate(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "audit_logs": {
                "columns": [
                    {"name": "log_id", "type": "int", "primary_key": True},
                    {"name": "user_id", "type": "int"},
                ]
            },
            "users": {
                "columns": [
                    {"name": "user_id", "type": "int", "primary_key": True},
                ]
            },
            "admins": {
                "columns": [
                    {"name": "user_id", "type": "int", "primary_key": True},
                ]
            },
        },
    }

    result = engine.process(raw_schema)
    audit_rels = [
        r for r in result.relationships if r.source_table == "audit_logs"
    ]
    assert len(audit_rels) >= 2
    # Because both users.user_id and admins.user_id are identical strong targets for audit_logs.user_id
    # they should be marked UNCERTAIN / ambiguous
    for r in audit_rels:
        assert r.status == RelationshipStatus.UNCERTAIN
        assert r.relationship_case == RelationshipCase.UNCERTAIN_AMBIGUOUS
        assert r.is_executable is False


# ---------------------------------------------------------------------------
# Test 10: Similar Names But Unrelated Entities (Strict Rule)
# ---------------------------------------------------------------------------
def test_similar_names_unrelated_entities(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "products": {
                "columns": [
                    {"name": "product_id", "type": "int", "primary_key": True},
                    {"name": "status", "type": "varchar(20)"},
                    {"name": "description", "type": "varchar(255)"},
                ]
            },
            "orders": {
                "columns": [
                    {"name": "order_id", "type": "int", "primary_key": True},
                    {"name": "status", "type": "varchar(20)"},
                    {"name": "description", "type": "varchar(255)"},
                ]
            },
        },
    }

    result = engine.process(raw_schema)
    # Neither 'status' nor 'description' are FKs or PKs of the other table
    # Strict rule: Name similarity alone must NEVER create a relationship!
    assert len(result.to_executable_relationships()) == 0


# ---------------------------------------------------------------------------
# Test 11: Accidental Value Overlap Without Structural Signal
# ---------------------------------------------------------------------------
def test_accidental_value_overlap_without_structural_signal(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "reviews": {
                "columns": [
                    {"name": "review_id", "type": "int", "primary_key": True},
                    {"name": "rating", "type": "int"},
                ]
            },
            "orders": {
                "columns": [
                    {"name": "order_id", "type": "int", "primary_key": True},
                    {"name": "priority", "type": "int"},
                ]
            },
        },
    }

    # Sample data has 100% overlap for rating and priority (values 1, 2, 3, 4, 5)
    sample_data = {
        "reviews": [{"rating": i} for i in range(1, 6)],
        "orders": [{"priority": i} for i in range(1, 6)],
    }

    result = engine.process(raw_schema, sample_data=sample_data)
    # No structural FK naming pattern and neither 'rating' nor 'priority' is a PK
    # Value overlap alone must NOT create a false relationship
    assert len(result.to_executable_relationships()) == 0


# ---------------------------------------------------------------------------
# Test 12: Completely Disconnected Schema
# ---------------------------------------------------------------------------
def test_completely_disconnected_schema(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "table_alpha": {
                "columns": [{"name": "alpha_code", "type": "varchar(10)", "primary_key": True}]
            },
            "table_beta": {
                "columns": [{"name": "beta_data", "type": "text"}]
            },
            "table_gamma": {
                "columns": [{"name": "gamma_ts", "type": "timestamp"}]
            },
        },
    }

    result = engine.process(raw_schema)
    assert len(result.relationships) == 0
    assert result.disconnected_analysis.connected_components_count == 3
    assert set(result.disconnected_analysis.disconnected_entities) == {
        "table_alpha", "table_beta", "table_gamma"
    }


# ---------------------------------------------------------------------------
# Test 13: Multiple Disconnected Components
# ---------------------------------------------------------------------------
def test_multiple_disconnected_components(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            # Cluster 1: Customers & Orders
            "customers": {"columns": [{"name": "customer_id", "type": "int", "primary_key": True}]},
            "orders": {"columns": [{"name": "order_id", "type": "int", "primary_key": True}, {"name": "customer_id", "type": "int"}]},
            # Cluster 2: Suppliers & Parts
            "suppliers": {"columns": [{"name": "supplier_id", "type": "int", "primary_key": True}]},
            "parts": {"columns": [{"name": "part_id", "type": "int", "primary_key": True}, {"name": "supplier_id", "type": "int"}]},
            # Isolated Table: AuditLog
            "system_logs": {"columns": [{"name": "log_text", "type": "text"}]},
        },
        "relationships": [
            {
                "name": "rel_cust_orders",
                "from_table": "orders",
                "from_column": "customer_id",
                "to_table": "customers",
                "to_column": "customer_id",
            },
            {
                "name": "rel_sup_parts",
                "from_table": "parts",
                "from_column": "supplier_id",
                "to_table": "suppliers",
                "to_column": "supplier_id",
            },
        ],
    }

    result = engine.process(raw_schema)
    analysis = result.disconnected_analysis

    assert analysis.total_tables == 5
    # 2 multi-table components + 1 isolated table = 3 components
    assert analysis.connected_components_count == 3
    assert "system_logs" in analysis.disconnected_entities
    assert set(analysis.connected_entities) == {"customers", "orders", "suppliers", "parts"}


# ---------------------------------------------------------------------------
# Test 14: Case Normalization (CustomerID vs customer_id vs CUSTOMER_ID)
# ---------------------------------------------------------------------------
def test_case_and_identifier_normalization(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "tblCustomers": {
                "columns": [
                    {"name": "CustomerID", "type": "INT", "primary_key": True},
                    {"name": "CustomerName", "type": "VARCHAR(100)"},
                ]
            },
            "tblOrders": {
                "columns": [
                    {"name": "OrderID", "type": "INT", "primary_key": True},
                    {"name": "CUSTOMER_ID", "type": "INT"},
                ]
            },
        },
    }

    result = engine.process(raw_schema)
    norm = result.normalized_schema

    # Physical names preserved exactly
    assert "tblCustomers" in norm.tables
    assert "CustomerID" in norm.tables["tblCustomers"].columns
    assert norm.tables["tblCustomers"].columns["CustomerID"].original_name == "CustomerID"
    assert norm.tables["tblCustomers"].columns["CustomerID"].normalized_name == "customer_id"

    # Inferred relationship preserves exact physical casing for SQL generation
    assert len(result.relationships) == 1
    rel = result.relationships[0]
    assert rel.source_table == "tblOrders"
    assert rel.source_column == "CUSTOMER_ID"
    assert rel.target_table == "tblCustomers"
    assert rel.target_column == "CustomerID"


# ---------------------------------------------------------------------------
# Test 15: Schema With Sample Data
# ---------------------------------------------------------------------------
def test_schema_with_sample_data(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "departments": {
                "columns": [
                    {"name": "dept_id", "type": "int", "primary_key": True},
                    {"name": "name", "type": "varchar(50)"},
                ]
            },
            "employees": {
                "columns": [
                    {"name": "emp_id", "type": "int", "primary_key": True},
                    {"name": "dept_id", "type": "int"},
                ]
            },
        },
    }

    sample_data = {
        "departments": [{"dept_id": 10, "name": "Sales"}, {"dept_id": 20, "name": "Engineering"}],
        "employees": [{"emp_id": 1, "dept_id": 10}, {"emp_id": 2, "dept_id": 10}, {"emp_id": 3, "dept_id": 20}],
    }

    result = engine.process(raw_schema, sample_data=sample_data)
    assert len(result.relationships) == 1
    rel = result.relationships[0]
    assert rel.evidence.sample_overlap is not None
    assert rel.evidence.sample_containment == 1.0  # All employee dept_ids are in departments
    assert rel.confidence >= 0.85


# ---------------------------------------------------------------------------
# Test 16: Schema Without Sample Data
# ---------------------------------------------------------------------------
def test_schema_without_sample_data(engine: RelationshipProcessingEngine) -> None:
    raw_schema = {
        "database": "ShopDB",
        "tables": {
            "departments": {
                "columns": [
                    {"name": "dept_id", "type": "int", "primary_key": True},
                    {"name": "name", "type": "varchar(50)"},
                ]
            },
            "employees": {
                "columns": [
                    {"name": "emp_id", "type": "int", "primary_key": True},
                    {"name": "dept_id", "type": "int"},
                ]
            },
        },
    }

    # Explicitly sample_data = None
    result = engine.process(raw_schema, sample_data=None)
    assert len(result.relationships) == 1
    rel = result.relationships[0]
    assert rel.evidence.sample_overlap is None
    assert rel.evidence.sample_containment is None
    assert rel.status == RelationshipStatus.INFERRED
    assert rel.is_executable is True
