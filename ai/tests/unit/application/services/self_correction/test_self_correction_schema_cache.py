from __future__ import annotations

import concurrent.futures
from unittest.mock import Mock
import pytest

from src.application.dto.self_correction.critic_result import CriticIssue, CriticResult
from src.application.ports.physical_schema_repository import PhysicalSchemaRepository
from src.application.services.self_correction.critic_finding_verifier import (
    CriticFindingVerifier,
)
from src.application.services.self_correction.self_correction_service import (
    SelfCorrectionService,
)
from src.application.services.self_correction.validators.sql_relationship_validator import (
    SQLRelationshipValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.infrastructure.semantic_layer.ingestion.schema_loader import SchemaLoader


def _dummy_schema(database: str = "TestDB", table_name: str = "customers") -> dict:
    return {
        "database": database,
        "tables": {
            table_name: {
                "columns": [
                    {"name": "id", "type": "int", "primary_key": True},
                    {"name": "name", "type": "varchar", "primary_key": False},
                ]
            }
        },
        "relationships": [],
    }


class FakeContext:
    def build_llm_context(self, question: str) -> str:
        return "fake_context"


class FakeSemanticRepo:
    def load(self) -> dict:
        return {"relationships": []}


class FakeCorrectionService:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls = []

    def correct(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return next(self._responses)


def _build_service(
    mock_schema_provider: PhysicalSchemaRepository,
    critic_results: list[CriticResult],
    correction_responses: list[str] | None = None,
) -> tuple[SelfCorrectionService, Mock, FakeCorrectionService]:
    syntax_validator = SQLSyntaxValidator()
    schema_validator = SQLSchemaValidator(
        schema_provider=mock_schema_provider,
        syntax_validator=syntax_validator,
    )
    relationship_validator = SQLRelationshipValidator(
        semantic_repository=FakeSemanticRepo(),
        syntax_validator=syntax_validator,
        schema_validator=schema_validator,
    )

    mock_critic_service = Mock()
    mock_critic_service.evaluate.side_effect = critic_results

    finding_verifier = CriticFindingVerifier(schema_provider=mock_schema_provider)
    correction_service = FakeCorrectionService(correction_responses or [])

    service = SelfCorrectionService(
        context_retrieval_service=FakeContext(),
        syntax_validator=syntax_validator,
        schema_validator=schema_validator,
        relationship_validator=relationship_validator,
        critic_service=mock_critic_service,
        finding_verifier=finding_verifier,
        correction_service=correction_service,
        max_attempts=3,
        schema_provider=mock_schema_provider,
    )
    return service, mock_critic_service, correction_service


def test_1_multiple_schema_accesses_in_one_self_correction_run() -> None:
    """Test 1: Multiple schema accesses in one self-correction run.

    Verifies:
    - Underlying schema retrieval happens exactly ONCE.
    - Subsequent schema accesses across all retries/validators are cache hits.
    - All callers receive the exact same loaded schema structure.
    """
    mock_provider = Mock(spec=PhysicalSchemaRepository)
    loaded_schema = _dummy_schema()
    mock_provider.get_schema.return_value = loaded_schema

    # Attempt 0: Valid SQL -> Critic fails with an intent issue -> triggers correction
    # Correction generates: "SELECT c.name FROM customers AS c"
    # Attempt 1: Valid SQL -> Critic passes -> overall success!
    critic_results = [
        CriticResult(
            status="FAIL",
            issues=(CriticIssue(type="INTENT", description="Missing customer filter"),),
        ),
        CriticResult(status="PASS"),
    ]

    service, _, _ = _build_service(
        mock_provider,
        critic_results=critic_results,
        correction_responses=["SELECT c.name FROM customers AS c"],
    )

    outcome = service.run(
        question="Show customer name",
        sql="SELECT c.id FROM customers AS c",
    )

    assert outcome.is_valid is True
    assert outcome.attempts_used == 1
    assert outcome.sql == "SELECT c.name FROM customers AS c"

    # Schema retrieval must happen exactly ONCE across all attempts and validators
    assert mock_provider.get_schema.call_count == 1


def test_2_separate_self_correction_executions() -> None:
    """Test 2: Separate self-correction executions.

    Verifies:
    - Run #1 fetches Schema A (1 retrieval).
    - Run #2 fetches Schema B (1 retrieval).
    - Total retrieval count = 2.
    - Run #2 does NOT reuse Run #1's cached schema.
    """
    schema_a = _dummy_schema("DB_A", "customers_a")
    schema_b = _dummy_schema("DB_B", "customers_b")

    mock_provider = Mock(spec=PhysicalSchemaRepository)
    mock_provider.get_schema.side_effect = [schema_a, schema_b]

    service, _, _ = _build_service(
        mock_provider,
        critic_results=[CriticResult(status="PASS"), CriticResult(status="PASS")],
    )

    # Run #1: Valid against Schema A (table: customers_a)
    outcome_1 = service.run(
        question="Show customers A",
        sql="SELECT a.id FROM customers_a AS a",
    )
    assert outcome_1.is_valid is True
    assert mock_provider.get_schema.call_count == 1

    # Run #2: Valid against Schema B (table: customers_b)
    outcome_2 = service.run(
        question="Show customers B",
        sql="SELECT b.id FROM customers_b AS b",
    )
    assert outcome_2.is_valid is True
    assert mock_provider.get_schema.call_count == 2


def test_3_failed_schema_retrieval_is_not_cached() -> None:
    """Test 3: Failed schema retrieval.

    Verifies:
    - First retrieval failure raises an exception and is NOT cached.
    - Subsequent run attempts fresh retrieval against the provider.
    """
    mock_provider = Mock(spec=PhysicalSchemaRepository)
    mock_provider.get_schema.side_effect = [
        RuntimeError("Backend connection refused"),
        _dummy_schema(),
    ]

    service, _, _ = _build_service(
        mock_provider,
        critic_results=[CriticResult(status="PASS")],
    )

    # First run: Fails immediately with RuntimeError
    with pytest.raises(RuntimeError, match="Backend connection refused"):
        service.run("Show customer", "SELECT c.id FROM customers AS c")

    assert mock_provider.get_schema.call_count == 1

    # Second run: Backend recovers, retrieval succeeds, query validates
    outcome = service.run("Show customer", "SELECT c.id FROM customers AS c")
    assert outcome.is_valid is True
    assert mock_provider.get_schema.call_count == 2


def test_4_concurrent_executions_do_not_share_cached_state() -> None:
    """Test 4: Concurrent/request isolation.

    Verifies that simultaneous SelfCorrectionService.run() executions across
    threads each have their own isolated execution cache and do not contaminate
    or see each other's schema.
    """
    schema_1 = _dummy_schema("DB_1", "users_1")
    schema_2 = _dummy_schema("DB_2", "orders_2")

    provider_1 = Mock(spec=PhysicalSchemaRepository)
    provider_1.get_schema.return_value = schema_1

    provider_2 = Mock(spec=PhysicalSchemaRepository)
    provider_2.get_schema.return_value = schema_2

    service_1, _, _ = _build_service(provider_1, [CriticResult(status="PASS")])
    service_2, _, _ = _build_service(provider_2, [CriticResult(status="PASS")])

    def run_job(service: SelfCorrectionService, sql: str) -> bool:
        outcome = service.run(question="Query", sql=sql)
        return outcome.is_valid

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_1 = executor.submit(run_job, service_1, "SELECT u.id FROM users_1 AS u")
        future_2 = executor.submit(run_job, service_2, "SELECT o.id FROM orders_2 AS o")

        res_1 = future_1.result(timeout=5)
        res_2 = future_2.result(timeout=5)

    assert res_1 is True
    assert res_2 is True
    assert provider_1.get_schema.call_count == 1
    assert provider_2.get_schema.call_count == 1
