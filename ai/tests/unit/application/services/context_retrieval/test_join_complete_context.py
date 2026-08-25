from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)


class FakeSemanticRepository:
    def __init__(self) -> None:
        self.requested_top_k: int | None = None
        self._layer = {
            "entities": [
    {"name": "Customer", "mapping": "customers"},
    {"name": "Account", "mapping": "accounts"},
    {"name": "Branch", "mapping": "branches"},
    {"name": "Transaction", "mapping": "transactions"},
    {"name": "Card", "mapping": "cards"},
    {"name": "Loan", "mapping": "loans"},
    {"name": "Merchant", "mapping": "merchants"},
],
            "dimensions": [
                {"name": "Customer First Name", "mapping": "customers.first_name"},
                {"name": "Customer Last Name", "mapping": "customers.last_name"},
                {"name": "Account Balance", "mapping": "accounts.balance_usd"},
                {"name": "Transaction ID", "mapping": "transactions.transaction_id"},
                {"name": "Card ID", "mapping": "cards.card_id"},
                {"name": "Loan Amount", "mapping": "loans.loan_amount"},
            ],
            "measures": [],
           "relationships": [
    {
        "name": "customers_accounts",
        "from_table": "customers",
        "from_column": "customer_id",
        "to_table": "accounts",
        "to_column": "customer_id",
    },
    {
        "name": "branches_accounts",
        "from_table": "branches",
        "from_column": "branch_id",
        "to_table": "accounts",
        "to_column": "branch_id",
    },
    {
        "name": "accounts_transactions",
        "from_table": "accounts",
        "from_column": "account_id",
        "to_table": "transactions",
        "to_column": "account_id",
    },
    {
        "name": "accounts_cards",
        "from_table": "accounts",
        "from_column": "account_id",
        "to_table": "cards",
        "to_column": "account_id",
    },
    {
        "name": "customers_loans",
        "from_table": "customers",
        "from_column": "customer_id",
        "to_table": "loans",
        "to_column": "customer_id",
    },
],
        }

    def retrieve(self, question: str, top_k: int):
        self.requested_top_k = top_k
        return [
            {"type": "entity", "payload": {"mapping": "transactions"}},
            {"type": "dimension", "payload": {"mapping": "accounts.balance_usd"}},
        ]

    def load(self):
        return self._layer


def test_context_includes_columns_and_join_path_between_retrieved_tables() -> None:
    context = ContextRetrievalService(FakeSemanticRepository()).build_llm_context(
        "Show every transaction with customer name and account balance."
    )

    assert "customers.first_name" not in context  # Context uses concise table-qualified sections.
    assert "balance_usd (Account Balance)" in context
    assert "accounts.account_id -> transactions.account_id" in context
    assert "customers.customer_id -> accounts.customer_id" in context
    assert "QUERY SCOPE:" in context


def test_multi_table_question_expands_candidates_but_filters_context_to_explicit_tables() -> None:
    repository = FakeSemanticRepository()
    context = ContextRetrievalService(repository).build_llm_context(
        "Show each customer account transaction and the cards and loans for that customer."
    )

    # Five explicitly named approved entities require more than the default
    # eight independently-indexed semantic documents for reliable coverage.
    assert repository.requested_top_k == 20
    assert "TABLE: customers" in context
    assert "TABLE: accounts" in context
    assert "TABLE: transactions" in context
    assert "ENTITY: Merchant -> merchants" not in context


def test_metric_phrase_plans_implicit_table_without_expanding_to_unrelated_entities() -> None:
    repository = FakeSemanticRepository()
    context = ContextRetrievalService(repository).build_llm_context(
        "Show the average account balance by customer."
    )

    assert repository.requested_top_k == 8
    assert "ENTITY: Customer -> customers" in context
    assert "ENTITY: Account -> accounts" in context
    assert "ENTITY: Merchant -> merchants" not in context


def test_multi_fanout_context_includes_safe_aggregation_guidance() -> None:
    context = ContextRetrievalService(FakeSemanticRepository()).build_llm_context(
        "Show each customer account transaction cards and loans."
    )

    assert "SAFE AGGREGATION:" in context
    assert "separate CTE or subquery" in context
class ConfigurableFakeSemanticRepository(FakeSemanticRepository):
    """FakeSemanticRepository with an overridable retrieve() result set,
    for tests that need retrieval to differ from the fixed default."""

    def __init__(self, retrieve_results):
        super().__init__()
        self._retrieve_results = retrieve_results

    def retrieve(self, question: str, top_k: int):
        self.requested_top_k = top_k
        return self._retrieve_results


def test_proper_name_question_retains_semantically_retrieved_customer_table() -> None:
    repository = ConfigurableFakeSemanticRepository(
        retrieve_results=[
            {"type": "entity", "payload": {"mapping": "customers"}},
            {"type": "entity", "payload": {"mapping": "accounts"}},
            {"type": "entity", "payload": {"mapping": "branches"}},
        ]
    )

    context = ContextRetrievalService(repository).build_llm_context(
        "show me all the accounts in Sergio Parker's branch"
    )

    # Customer is retrieved semantically even though "customer" never
    # appears literally in the question.
    assert "TABLE: customers" in context
    assert "TABLE: accounts" in context

    # Branch is required and survives into the approved query scope.
    assert "Required tables: accounts, branches, customers" in context

    # Both required join paths are present.
    assert "customers.customer_id -> accounts.customer_id" in context
    assert "branches.branch_id -> accounts.branch_id" in context


def test_explicit_lexical_tables_no_longer_suppress_retrieved_table() -> None:
    repository = ConfigurableFakeSemanticRepository(
        retrieve_results=[
            {"type": "entity", "payload": {"mapping": "customers"}},
        ]
    )

    context = ContextRetrievalService(repository).build_llm_context(
        "show me the accounts in the branch"
    )

    assert "TABLE: accounts" in context
    assert "TABLE: customers" in context

    # Branch is represented in the required scope and relationship graph.
    assert "Required tables: accounts, branches, customers" in context
    assert "branches.branch_id -> accounts.branch_id" in context
    assert "customers.customer_id -> accounts.customer_id" in context


def test_complex_query_retains_retrieved_cards_and_loans() -> None:
    # Regression for Test Case 1: a long, multi-clause question can still
    # miss "cards"/"loans" lexically; retrieval must fill the gap and the
    # merge must preserve both, plus their relationships to already-seeded
    # tables.
    repository = ConfigurableFakeSemanticRepository(retrieve_results=[
        {"type": "entity", "payload": {"mapping": "cards"}},
        {"type": "entity", "payload": {"mapping": "loans"}},
    ])
    context = ContextRetrievalService(repository).build_llm_context(
        "identify customers with accounts at branches in a different city, "
        "their card and loan totals, and their most frequent merchant"
    )

    assert "TABLE: cards" in context
    assert "TABLE: loans" in context
    assert "accounts.account_id -> cards.account_id" in context
    assert "customers.customer_id -> loans.customer_id" in context


def test_no_lexical_match_still_uses_semantic_retrieval_fallback() -> None:
    # Existing fallback path (requested_tables empty) is unchanged: a
    # question with no lexical table/entity matches resolves solely from
    # the vector-retrieved results, same as before this patch.
    repository = FakeSemanticRepository()
    context = ContextRetrievalService(repository).build_llm_context(
        "what happened recently"
    )

    assert "TABLE: transactions" in context
    assert "TABLE: accounts" in context


def test_unsupported_question_with_no_retrieval_fabricates_no_tables() -> None:
    # No lexical match and no retrieved results must not synthesize table
    # coverage. This is the layer-level guarantee that lets the model
    # correctly return needs_clarification rather than guessing.
    repository = ConfigurableFakeSemanticRepository(retrieve_results=[])
    context = ContextRetrievalService(repository).build_llm_context(
        "xyzzy unrelated nonsense query"
    )

    assert "TABLE:" not in context
    assert "APPROVED RELATIONSHIPS:" not in context