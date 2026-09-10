"""Unit test suite verifying all Conversation Layer fixes and enhancements.

Covers:
1. Tolerant Reader for Backend / .NET payload contracts
2. Summary Replay (Arabic and English)
3. Multi-Row & Entity inspection ('الخمسة دول', 'بيانات سارة')
4. Negative Caching (<10ms instant replay without re-running Text-to-SQL)
5. Optimistic Semantic Intent Routing (avoiding false AMBIGUOUS trips)
6. Dialog Continuation with Pending Clarification
"""

import pytest
from unittest.mock import MagicMock

from src.application.dto.backend.copilot.text_to_sql_runtime_response import (
    TextToSQLRuntimeResponse,
)
from src.application.services.conversation.persistence.backend_state_adapter import (
    BackendStateAdapter,
)
from src.application.services.conversation.result_resolution.models import (
    ResultResolutionStatus,
)
from src.application.services.conversation.result_resolution.result_resolver import (
    ResultResolver,
)
from src.application.services.conversation.router.conversation_router import (
    ConversationRouter,
)
from src.application.services.conversation.router.routing_decision import (
    ConversationRoute,
)
from src.application.services.conversation.semantic_routing.application.semantic_intent_router import (
    SemanticIntentRouter,
)
from src.application.services.conversation.semantic_routing.domain.intent import (
    ConversationIntent,
)
from src.application.services.conversation.state.conversation_state import (
    ConversationState,
    ResultMetadata,
)
from src.application.services.conversation.state.state_manager import (
    ConversationStateManager,
)


# ==============================================================================
# 1. Tolerant Reader Tests
# ==============================================================================
class TestBackendStateAdapterTolerantReader:
    def test_parses_dotnet_nested_table_data(self):
        payload = {
            "queryId": "q123",
            "question": "Show top 5 employees",
            "generatedSql": "SELECT Name, Salary FROM Employees",
            "result": {
                "TableData": {
                    "Columns": ["Name", "Salary"],
                    "Rows": [
                        ["Sara", 15000],
                        ["Tamer", 12000],
                    ],
                    "TotalRows": 2,
                },
                "TextSummary": "Top 2 employees by salary are Sara and Tamer.",
            },
        }
        state = BackendStateAdapter.extract_state(
            "conv_dotnet_1",
            (),
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata_dict=payload,
        )
        assert state.last_result_metadata is not None
        assert state.last_result_metadata.columns == ("Name", "Salary")
        assert len(state.last_result_metadata.sample_rows) == 2
        assert state.last_result_metadata.row_count == 2
        assert state.last_result_metadata.summary == "Top 2 employees by salary are Sara and Tamer."

    def test_parses_flat_root_fields(self):
        payload = {
            "columns": ["Dept", "Budget"],
            "rows": [["IT", 500000]],
            "rowCount": 1,
            "summary": "IT department budget is 500000",
        }
        state = BackendStateAdapter.extract_state(
            "conv_flat_1",
            (),
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata_dict=payload,
        )
        assert state.last_result_metadata is not None
        assert state.last_result_metadata.columns == ("Dept", "Budget")
        assert state.last_result_metadata.sample_rows == (("IT", 500000),)
        assert state.last_result_metadata.row_count == 1
        assert state.last_result_metadata.summary == "IT department budget is 500000"

    def test_parses_data_list_of_dicts(self):
        payload = {
            "data": [
                {"Product": "Laptop", "Price": 1200},
                {"Product": "Mouse", "Price": 25},
            ],
            "totalRows": 2,
        }
        state = BackendStateAdapter.extract_state(
            "conv_dicts_1",
            (),
            tenant_id="tenant_1",
            user_id="user_1",
            last_result_metadata_dict=payload,
        )
        assert state.last_result_metadata is not None
        assert "Product" in state.last_result_metadata.columns
        assert "Price" in state.last_result_metadata.columns
        assert len(state.last_result_metadata.sample_rows) == 2


# ==============================================================================
# 2. Summary Replay Tests
# ==============================================================================
class TestSummaryReplay:
    @pytest.fixture
    def metadata_with_summary(self):
        return ResultMetadata(
            columns=("Customer", "Balance"),
            row_count=2,
            sample_rows=(("Acme", 5000), ("Beta", 3000)),
            summary="ملخص النتائج: إجمالي المبيعات لشركة Acme هو 5000 ولشركة Beta هو 3000.",
        )

    def test_replay_summary_arabic_variations(self, metadata_with_summary):
        resolver = ResultResolver()
        for q in ["عيد الملخص", "لخص النتيجة", "الملخص التنفيذي", "وريني الملخص"]:
            outcome = resolver.resolve(q, metadata_with_summary)
            assert outcome.status == ResultResolutionStatus.ANSWERABLE
            assert "ملخص النتائج" in outcome.answer

    def test_replay_summary_english_variations(self, metadata_with_summary):
        resolver = ResultResolver()
        for q in ["repeat the summary", "executive summary", "what was the summary", "show me the summary"]:
            outcome = resolver.resolve(q, metadata_with_summary)
            assert outcome.status == ResultResolutionStatus.ANSWERABLE
            assert "ملخص النتائج" in outcome.answer

    def test_summary_missing_returns_not_answerable(self):
        resolver = ResultResolver()
        metadata_no_summary = ResultMetadata(
            columns=("Customer", "Balance"),
            row_count=2,
            sample_rows=(("Acme", 5000), ("Beta", 3000)),
            summary=None,
        )
        outcome = resolver.resolve("عيد الملخص", metadata_no_summary)
        assert outcome.status == ResultResolutionStatus.NOT_ANSWERABLE


# ==============================================================================
# 3. Multi-Row & Entity Inspection Tests
# ==============================================================================
class TestMultiRowAndEntityInspection:
    @pytest.fixture
    def sample_table_metadata(self):
        return ResultMetadata(
            columns=("Name", "Department", "Salary"),
            row_count=3,
            sample_rows=(
                ("Sara", "Engineering", 15000),
                ("Ahmed", "Sales", 12000),
                ("Khaled", "Marketing", 11000),
            ),
        )

    def test_list_all_rows_arabic_and_english(self, sample_table_metadata):
        resolver = ResultResolver()
        for q in ["الخمسة دول", "مين هما", "اعرض النتائج", "who are they", "list them", "show the results"]:
            outcome = resolver.resolve(q, sample_table_metadata)
            assert outcome.status == ResultResolutionStatus.ANSWERABLE
            assert "Sara" in outcome.answer
            assert "Ahmed" in outcome.answer
            assert "Khaled" in outcome.answer

    def test_entity_row_inspection_arabic(self, sample_table_metadata):
        resolver = ResultResolver()
        outcome = resolver.resolve("بيانات سارة", sample_table_metadata)
        assert outcome.status == ResultResolutionStatus.ANSWERABLE
        assert "Sara" in outcome.answer
        assert "15000" in outcome.answer
        assert "Engineering" in outcome.answer

    def test_entity_row_inspection_english(self, sample_table_metadata):
        resolver = ResultResolver()
        outcome = resolver.resolve("Tell me about Ahmed", sample_table_metadata)
        assert outcome.status == ResultResolutionStatus.ANSWERABLE
        assert "Ahmed" in outcome.answer
        assert "12000" in outcome.answer
        assert "Sales" in outcome.answer

    def test_entity_specific_column_lookup(self, sample_table_metadata):
        resolver = ResultResolver()
        outcome = resolver.resolve("What is Sara's salary?", sample_table_metadata)
        assert outcome.status == ResultResolutionStatus.ANSWERABLE
        assert outcome.answer == "15000"


# ==============================================================================
# 4. Negative Caching Tests
# ==============================================================================
class TestNegativeCaching:
    def test_negative_result_fast_replay(self):
        router = ConversationRouter()
        mock_executor = MagicMock()
        mock_executor.return_value = TextToSQLRuntimeResponse.failure(
            error_code="TABLE_NOT_FOUND",
            message="Table 'NonExistent' does not exist in schema.",
        )

        conv_id = "conv_neg_test"
        question = "Show data from non existent table"

        # Turn 1: Fails at Text-to-SQL, records negative result
        decision_1 = router.route(
            question,
            conversation_id=conv_id,
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor,
        )
        assert decision_1.route == ConversationRoute.EXECUTION_ERROR
        assert decision_1.is_success is False
        assert mock_executor.call_count == 1

        # Turn 2: Exact same question should HIT negative cache without calling executor!
        decision_2 = router.route(
            question,
            conversation_id=conv_id,
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor,
        )
        assert decision_2.route == ConversationRoute.EXACT_REPLAY
        assert decision_2.cache_hit is True
        assert decision_2.cache_type == "NEGATIVE_REPLAY"
        # Crucial: executor must NOT have been called again!
        assert mock_executor.call_count == 1


# ==============================================================================
# 5. Semantic Router Optimistic Routing
# ==============================================================================
class TestOptimisticSemanticRouting:
    def test_close_margin_with_context_does_not_force_ambiguous(self):
        router = SemanticIntentRouter.get_shared_instance()
        state = ConversationState("conv_margin_test")
        state.active_query_state = MagicMock()

        # Follow-up query in active context
        res = router.classify("Sort them by salary descending", state=state, has_history=True)
        assert res.intent != ConversationIntent.AMBIGUOUS
        assert not res.is_ambiguous

    def test_genuine_ambiguity_still_flagged(self):
        router = SemanticIntentRouter.get_shared_instance()
        state = ConversationState("conv_margin_test_2")
        res = router.classify("What about it?", state=state, has_history=True)
        assert res.intent == ConversationIntent.AMBIGUOUS
        assert res.is_ambiguous is True


# ==============================================================================
# 6. Dialog Continuation Tests
# ==============================================================================
class TestDialogContinuation:
    def test_pending_clarification_merges_on_next_turn(self):
        router = ConversationRouter()
        mock_executor = MagicMock()

        # Turn 1 returns NeedsClarification
        mock_executor.return_value = TextToSQLRuntimeResponse(
            status="NeedsClarification",
            sql=None,
            message="Which branch do you want: Cairo or Alexandria?",
        )

        conv_id = "conv_dialog_test"
        dec_1 = router.route(
            "Show total sales",
            conversation_id=conv_id,
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor,
        )
        assert dec_1.route == ConversationRoute.UNRESOLVED_CONTEXT
        state = router.state_manager.get_state(conv_id)
        assert state.pending_clarification is not None

        # Turn 2: User answers "Alexandria"
        mock_executor.return_value = TextToSQLRuntimeResponse.success(
            "SELECT SUM(Sales) FROM Orders WHERE Branch = 'Alexandria'"
        )
        dec_2 = router.route(
            "Alexandria",
            conversation_id=conv_id,
            tenant_id="tenant_1",
            user_id="user_1",
            executor=mock_executor,
        )
        # Executor was invoked with the merged question
        assert mock_executor.call_count == 2
        called_question = mock_executor.call_args[0][0].question
        assert "Show total sales" in called_question
        assert "Alexandria" in called_question
