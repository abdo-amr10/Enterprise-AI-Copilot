"""
Comprehensive Domain-Agnostic Semantic Routing and Conversation Layer Test Suite.

Validates that semantic routing, slot extraction, follow-up detection, and
result resolution operate purely on linguistic and structural patterns without
coupling to the banking domain.

Evaluates:
  1. Banking (baseline domain)
  2. Healthcare (patients, doctors, dosage, pediatrics, oncology)
  3. Human Resources (employees, salary, department, job title)
  4. E-Commerce (products, units sold, tablets, order volume)
  5. Synthetic / Alien domain (zentars, flarix, norv, krells)
"""

import pytest
from unittest.mock import MagicMock

from src.application.dto.backend.copilot.copilot_ask_request import CopilotAskRequest
from src.application.dto.backend.copilot.text_to_sql_runtime_response import TextToSQLRuntimeResponse
from src.application.services.conversation.extraction.slot_extractor import SlotExtractor
from src.application.services.conversation.followup.followup_detector import FollowupDetector
from src.application.services.conversation.followup.models import FollowupConfidence, FollowupType
from src.application.services.conversation.result_resolution.models import (
    ResultResolutionOutcome,
    ResultResolutionStatus,
)
from src.application.services.conversation.result_resolution.result_resolver import ResultResolver
from src.application.services.conversation.router.conversation_router import ConversationRouter
from src.application.services.conversation.router.routing_decision import (
    ConversationRoute,
    RoutingDecision,
)
from src.application.services.conversation.semantic_routing.application.semantic_intent_router import (
    SemanticIntentRouter,
)
from src.application.services.conversation.semantic_routing.domain.intent import ConversationIntent
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ResultMetadata,
)


class MockExecutor:
    """Mock Text-to-SQL executor tracking invocations and input requests."""

    def __init__(self) -> None:
        self.invocations: list[CopilotAskRequest] = []
        self.next_sql: str = "SELECT * FROM MockTable"

    def run(self, request: CopilotAskRequest) -> TextToSQLRuntimeResponse:
        self.invocations.append(request)
        return TextToSQLRuntimeResponse.success(self.next_sql)


@pytest.fixture(scope="module")
def shared_router() -> SemanticIntentRouter:
    return SemanticIntentRouter.get_shared_instance()


@pytest.fixture
def mock_executor() -> MockExecutor:
    return MockExecutor()


@pytest.fixture
def conv_router(shared_router: SemanticIntentRouter) -> ConversationRouter:
    return ConversationRouter(semantic_router=shared_router)


# ==============================================================================
# 1. Semantic Intent Classification across Multiple Domains
# ==============================================================================
class TestCrossDomainIntentClassification:
    """Verify that intent classification is invariant to domain vocabulary."""

    @pytest.mark.parametrize(
        "domain,query,expected_intent",
        [
            # Banking
            ("Banking", "Show all transactions above 1000", ConversationIntent.NEW_DATABASE_QUERY),
            ("Banking", "Filter by checking accounts only", ConversationIntent.FILTER_CHANGE),
            ("Banking", "Top ten only", ConversationIntent.LIMIT_CHANGE),
            ("Banking", "Sort by balance descending", ConversationIntent.SORT_CHANGE),
            ("Banking", "Group by account type", ConversationIntent.GROUP_BY_CHANGE),
            # Healthcare
            ("Healthcare", "Show all patients admitted to pediatrics", ConversationIntent.NEW_DATABASE_QUERY),
            ("Healthcare", "Filter by cardiology cases only", ConversationIntent.FILTER_CHANGE),
            ("Healthcare", "Cap the list to eight patients", ConversationIntent.LIMIT_CHANGE),
            ("Healthcare", "Order by dosage descending", ConversationIntent.SORT_CHANGE),
            ("Healthcare", "Break down by hospital wing", ConversationIntent.GROUP_BY_CHANGE),
            # Human Resources
            ("HR", "List all employees in engineering", ConversationIntent.NEW_DATABASE_QUERY),
            ("HR", "Only full time staff", ConversationIntent.FILTER_CHANGE),
            ("HR", "Limit to fifteen rows", ConversationIntent.LIMIT_CHANGE),
            ("HR", "Sort by base salary from highest to lowest", ConversationIntent.SORT_CHANGE),
            ("HR", "Partition by department", ConversationIntent.GROUP_BY_CHANGE),
            # E-Commerce
            ("E-Commerce", "Find all products with negative profit margins", ConversationIntent.NEW_DATABASE_QUERY),
            ("E-Commerce", "What about in the electronics category?", ConversationIntent.FILTER_CHANGE),
            ("E-Commerce", "First three items", ConversationIntent.LIMIT_CHANGE),
            ("E-Commerce", "Arrange by units sold ascending", ConversationIntent.SORT_CHANGE),
            ("E-Commerce", "Group by warehouse location", ConversationIntent.GROUP_BY_CHANGE),
            # Synthetic Alien Domain
            ("Alien", "Query all zentars in the database", ConversationIntent.NEW_DATABASE_QUERY),
            ("Alien", "Filter by flarix status only", ConversationIntent.FILTER_CHANGE),
            ("Alien", "Limit to seven records", ConversationIntent.LIMIT_CHANGE),
            ("Alien", "Order according to norv score desc", ConversationIntent.SORT_CHANGE),
            ("Alien", "Separate them by krell cluster", ConversationIntent.GROUP_BY_CHANGE),
        ],
    )
    def test_domain_agnostic_classification(
        self,
        shared_router: SemanticIntentRouter,
        domain: str,
        query: str,
        expected_intent: ConversationIntent,
    ):
        active_state = ConversationState(conversation_id="cross_domain_conv")
        active_state.last_successful_execution = {"sql": "SELECT 1"}
        res = shared_router.classify(query, state=active_state, has_history=True)
        assert res.intent == expected_intent, (
            f"Failed on domain '{domain}' with query '{query}'. Expected {expected_intent}, got {res.intent}"
        )


# ==============================================================================
# 2. Domain-Agnostic Slot Extraction
# ==============================================================================
class TestCrossDomainSlotExtraction:
    """Verify that slot extraction pulls the correct structural payload regardless of domain terms."""

    def test_healthcare_slots(self):
        assert SlotExtractor.extract_limit("I only want the top four patients") == "4"
        assert SlotExtractor.extract_filter("Filter by oncology patients only") == "oncology patients"
        assert SlotExtractor.extract_sort("Order by heart rate ascending") == "heart rate ascending"
        assert SlotExtractor.extract_group_by("Group according to physician") == "physician"
        assert SlotExtractor.extract_correction("Actually, make that above 150 mg") == "above 150 mg"

    def test_hr_slots(self):
        assert SlotExtractor.extract_limit("Show the first twenty employees") == "20"
        assert SlotExtractor.extract_filter("Only in the London office") == "London office"
        assert SlotExtractor.extract_sort("Sort by annual bonus desc") == "annual bonus desc"
        assert SlotExtractor.extract_group_by("Separate them by pay grade") == "pay grade"
        assert SlotExtractor.extract_correction("No, I meant senior engineers instead") == "senior engineers"

    def test_synthetic_alien_slots(self):
        assert SlotExtractor.extract_limit("Limit to twelve zentars") == "12"
        assert SlotExtractor.extract_filter("What about in Sector 9?") == "Sector 9"
        assert SlotExtractor.extract_sort("Rank by flarix intensity desc") == "flarix intensity desc"
        assert SlotExtractor.extract_group_by("Break down into norv bands") == "norv bands"
        assert SlotExtractor.extract_correction("Actually, change that to active krells") == "active krells"


# ==============================================================================
# 3. Dangling Entity Ambiguity Detection across Domains
# ==============================================================================
class TestDanglingEntityAmbiguityAcrossDomains:
    """Verify that 'And <entity>?' without prepositions or predicates is detected as ambiguous."""

    @pytest.mark.parametrize(
        "query,expected_entity",
        [
            ("And merchants?", "merchants"),
            ("And doctors?", "doctors"),
            ("And patients?", "patients"),
            ("And employees?", "employees"),
            ("And engineers?", "engineers"),
            ("And products?", "products"),
            ("And zentars?", "zentars"),
            ("And flarix?", "flarix"),
            ("And krells?", "krells"),
        ],
    )
    def test_dangling_entity_returns_unresolved(
        self,
        conv_router: ConversationRouter,
        mock_executor,
        query: str,
        expected_entity: str,
    ):
        resp = conv_router.route(
            query,
            conversation_id="conv_dangling",
            tenant_id="tenant_x",
            user_id="user_y",
            raw_conversation=({"role": "user", "content": "Show top 10 results."},),
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.UNRESOLVED_CONTEXT
        assert resp.is_success is False
        assert "clarify" in resp.error_message.lower()

    @pytest.mark.parametrize(
        "query",
        [
            "And in Chicago?",
            "And for February?",
            "And in pediatrics?",
            "And in Sector 9?",
            "And for 2024?",
        ],
    )
    def test_prepositional_and_temporal_and_phrases_are_not_ambiguous(
        self,
        conv_router: ConversationRouter,
        mock_executor,
        query: str,
    ):
        resp = conv_router.route(
            query,
            conversation_id="conv_preposition",
            tenant_id="tenant_x",
            user_id="user_y",
            raw_conversation=({"role": "user", "content": "Show all records."},),
            executor=mock_executor.run,
        )
        assert resp.route != ConversationRoute.UNRESOLVED_CONTEXT


# ==============================================================================
# 4. Result Resolution across Domains
# ==============================================================================
class TestResultResolutionAcrossDomains:
    """Verify ResultResolver computes counts, ranks, extremes, and cell lookups domain-agnostically."""

    def test_healthcare_extreme_and_count(self):
        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("PatientName", "Department", "DosageMG"),
            row_count=3,
            sample_rows=(
                ("Alice", "Pediatrics", 50.0),
                ("Bob", "Cardiology", 120.5),
                ("Charlie", "Oncology", 85.0),
            ),
        )

        # Count
        c_res = resolver.resolve("How many patients?", meta)
        assert c_res.status == ResultResolutionStatus.ANSWERABLE
        assert "3 rows" in c_res.answer

        # Extreme: Highest dosage
        e_res = resolver.resolve("Which patient has the highest dosage?", meta)
        assert e_res.status == ResultResolutionStatus.ANSWERABLE
        assert "Bob" in e_res.answer
        assert "120.5" in e_res.answer

        # Extreme: Lowest dosage
        low_res = resolver.resolve("Who has the lowest dosage?", meta)
        assert low_res.status == ResultResolutionStatus.ANSWERABLE
        assert "Alice" in low_res.answer

        # Cell lookup: Department
        cell_res = resolver.resolve("What department is Bob in?", meta)
        assert cell_res.status == ResultResolutionStatus.ANSWERABLE
        assert cell_res.answer == "Cardiology"

    def test_synthetic_alien_extreme_and_attribute(self):
        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("ZentarID", "GalaxySector", "NorvScore"),
            row_count=3,
            sample_rows=(
                ("Z-101", "Andromeda", 4200),
                ("Z-202", "Centauri", 9100),
                ("Z-303", "Kepler", 1500),
            ),
        )

        # Count
        c_res = resolver.resolve("How many zentars are there?", meta)
        assert c_res.status == ResultResolutionStatus.ANSWERABLE
        assert "3 rows" in c_res.answer

        # Extreme
        e_res = resolver.resolve("Which zentar has the maximum norv score?", meta)
        assert e_res.status == ResultResolutionStatus.ANSWERABLE
        assert "Z-202" in e_res.answer
        assert "9100" in e_res.answer

        # Cell lookup
        cell_res = resolver.resolve("What galaxy sector is Z-101 in?", meta)
        assert cell_res.status == ResultResolutionStatus.ANSWERABLE
        assert cell_res.answer == "Andromeda"

    def test_multi_numeric_column_ambiguity_in_healthcare(self):
        resolver = ResultResolver()
        meta = ResultMetadata(
            columns=("PatientName", "SystolicBP", "HeartRate"),
            row_count=2,
            sample_rows=(
                ("Alice", 120, 72),
                ("Bob", 140, 85),
            ),
        )
        # Without specifying whether systolic or heart rate is desired, must reject safely
        res = resolver.resolve("Which patient is highest?", meta)
        assert res.status == ResultResolutionStatus.NOT_ANSWERABLE
        assert "ambiguous" in (res.reason or "").lower()


# ==============================================================================
# 5. Multi-Turn Conversation Flows in Diverse Domains
# ==============================================================================
class TestMultiTurnFlowsAcrossDomains:
    """End-to-end multi-turn conversation tests in Healthcare and Synthetic domains."""

    def test_healthcare_multi_turn_flow(self, conv_router: ConversationRouter, mock_executor):
        conv_id = "conv_flow_health"

        # Turn 1: Initial query
        resp1 = conv_router.route(
            "Show all patients admitted to pediatrics.",
            conversation_id=conv_id,
            tenant_id="hospital_1",
            user_id="nurse_1",
            executor=mock_executor.run,
        )
        assert resp1.route == ConversationRoute.NEW_DATABASE_QUERY

        # Turn 2: Follow-up filter change
        resp2 = conv_router.route(
            "What about oncology?",
            conversation_id=conv_id,
            tenant_id="hospital_1",
            user_id="nurse_1",
            raw_conversation=({"role": "user", "content": "Show all patients admitted to pediatrics."},),
            executor=mock_executor.run,
        )
        assert resp2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "oncology" in (resp2.resolved_question or "").lower()

        # Turn 3: Follow-up limit change
        resp3 = conv_router.route(
            "Top five.",
            conversation_id=conv_id,
            tenant_id="hospital_1",
            user_id="nurse_1",
            raw_conversation=({"role": "user", "content": "Show all patients admitted to oncology."},),
            executor=mock_executor.run,
        )
        assert resp3.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "5" in (resp3.resolved_question or "")

        # Turn 4: Dangling entity -> clarify
        resp4 = conv_router.route(
            "And doctors?",
            conversation_id=conv_id,
            tenant_id="hospital_1",
            user_id="nurse_1",
            raw_conversation=({"role": "user", "content": "Top 5 patients admitted to oncology."},),
            executor=mock_executor.run,
        )
        assert resp4.route == ConversationRoute.UNRESOLVED_CONTEXT
        assert resp4.is_success is False

    def test_synthetic_alien_multi_turn_flow(self, conv_router: ConversationRouter, mock_executor):
        conv_id = "conv_flow_alien"

        # Turn 1: Initial query
        resp1 = conv_router.route(
            "Query all active zentars.",
            conversation_id=conv_id,
            tenant_id="alien_base",
            user_id="commander",
            executor=mock_executor.run,
        )
        assert resp1.route == ConversationRoute.NEW_DATABASE_QUERY

        # Turn 2: Follow-up sort
        resp2 = conv_router.route(
            "Sort by norv descending.",
            conversation_id=conv_id,
            tenant_id="alien_base",
            user_id="commander",
            raw_conversation=({"role": "user", "content": "Query all active zentars."},),
            executor=mock_executor.run,
        )
        assert resp2.route == ConversationRoute.FOLLOW_UP_QUERY
        assert "norv" in (resp2.resolved_question or "").lower()

        # Turn 3: Context reset
        resp3 = conv_router.route(
            "New question: list all krells.",
            conversation_id=conv_id,
            tenant_id="alien_base",
            user_id="commander",
            raw_conversation=({"role": "user", "content": "Query all active zentars sorted by norv descending."},),
            executor=mock_executor.run,
        )
        assert resp3.route == ConversationRoute.NEW_DATABASE_QUERY
        assert "krells" in mock_executor.invocations[-1].question.lower()


# ==============================================================================
# 6. Cross-Domain Scope Guard Rejections
# ==============================================================================
class TestCrossDomainScopeGuard:
    """Verify that general out-of-scope queries are rejected consistently regardless of domain framing."""

    @pytest.mark.parametrize(
        "query",
        [
            "Write a poem about medicine and hospitals",
            "Tell me a joke about employees",
            "What is the capital of France?",
            "What is the weather in London?",
            "Are you sentient or alive?",
        ],
    )
    def test_cross_domain_out_of_scope_rejection(
        self,
        conv_router: ConversationRouter,
        mock_executor,
        query: str,
    ):
        resp = conv_router.route(
            query,
            conversation_id="conv_scope_check",
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.UNSUPPORTED
        assert resp.is_success is False


# ==============================================================================
# 7. Explicit Domain Boundary Verification
# ==============================================================================
class TestExplicitDomainBoundaryVerification:
    """Explicit tests for domain-independence and schema grounding boundaries."""

    def test_banking_database_query(self, conv_router: ConversationRouter, mock_executor: MockExecutor):
        """Banking database query -> NEW_DATABASE_QUERY."""
        resp = conv_router.route(
            "Show customers with balance above 5000",
            conversation_id="conv_boundary_1",
            tenant_id="bank_tenant",
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        assert resp.is_success is True

    def test_foreign_domain_vocabulary_on_banking_database(self, conv_router: ConversationRouter, mock_executor: MockExecutor):
        """Foreign domain vocabulary on Banking database -> NEW_DATABASE_QUERY."""
        resp = conv_router.route(
            "Show doctors with the highest dosage",
            conversation_id="conv_boundary_2",
            tenant_id="bank_tenant",
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        assert resp.is_success is True

    def test_banking_vocabulary_on_another_domain(self, conv_router: ConversationRouter, mock_executor: MockExecutor):
        """Banking vocabulary on another domain -> NEW_DATABASE_QUERY."""
        resp = conv_router.route(
            "Show customers with the highest balance",
            conversation_id="conv_boundary_3",
            tenant_id="healthcare_tenant",
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        assert resp.is_success is True

    def test_dangling_followup(self, conv_router: ConversationRouter, mock_executor: MockExecutor):
        """Turn 1: Show customers, Turn 2: And doctors? -> UNRESOLVED_CONTEXT."""
        resp = conv_router.route(
            "And doctors?",
            conversation_id="conv_boundary_4",
            raw_conversation=({"role": "user", "content": "Show customers"},),
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.UNRESOLVED_CONTEXT
        assert resp.is_success is False

    def test_valid_followup(self, conv_router: ConversationRouter, mock_executor: MockExecutor):
        """Turn 1: Show customers in Cairo, Turn 2: What about Alexandria? -> FOLLOW_UP_QUERY."""
        resp = conv_router.route(
            "What about Alexandria?",
            conversation_id="conv_boundary_5",
            raw_conversation=({"role": "user", "content": "Show customers in Cairo"},),
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.FOLLOW_UP_QUERY
        assert resp.is_success is True
        assert "alexandria" in (resp.resolved_question or "").lower()

    def test_explicit_reset(self, conv_router: ConversationRouter, mock_executor: MockExecutor):
        """Turn 1: Show customers in Cairo, Turn 2: New question: show branches -> NEW_DATABASE_QUERY with prompt isolation."""
        resp = conv_router.route(
            "New question: show branches",
            conversation_id="conv_boundary_6",
            raw_conversation=(
                {"role": "user", "content": "Show customers in Cairo"},
                {"role": "assistant", "content": "Showing customers in Cairo."},
            ),
            executor=mock_executor.run,
        )
        assert resp.route == ConversationRoute.NEW_DATABASE_QUERY
        assert resp.is_success is True
        last_invocation = mock_executor.invocations[-1]
        assert "branches" in last_invocation.question.lower()
        # Prompt isolation guarantee: prior user/assistant conversation is NOT passed
        assert last_invocation.conversation == ()

