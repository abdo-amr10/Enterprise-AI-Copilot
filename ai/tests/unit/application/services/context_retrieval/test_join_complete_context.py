from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)


class FakeSemanticRepository:
    def __init__(self) -> None:
        self._layer = {
            "entities": [
                {"name": "Customer", "mapping": "customers"},
                {"name": "Account", "mapping": "accounts"},
                {"name": "Transaction", "mapping": "transactions"},
            ],
            "dimensions": [
                {"name": "Customer First Name", "mapping": "customers.first_name"},
                {"name": "Customer Last Name", "mapping": "customers.last_name"},
                {"name": "Account Balance", "mapping": "accounts.balance_usd"},
                {"name": "Transaction ID", "mapping": "transactions.transaction_id"},
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
                    "name": "accounts_transactions",
                    "from_table": "accounts",
                    "from_column": "account_id",
                    "to_table": "transactions",
                    "to_column": "account_id",
                },
            ],
        }

    def retrieve(self, question: str, top_k: int):
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
    assert "customers.customer_id -> accounts.customer_id" not in context
