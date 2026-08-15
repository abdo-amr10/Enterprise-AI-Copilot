from src.application.dto.backend.copilot.semantic_retrieval_request import (
    SemanticRetrievalRequest,
)
from src.application.pipelines.context_retrieval.semantic_retrieval_pipeline import (
    SemanticRetrievalPipeline,
)


class FakeRetrievalService:
    def retrieve(self, question: str, top_k: int | None = None):
        return [
            {
                "type": "relationship",
                "payload": {
                    "from_table": "customers",
                    "to_table": "accounts",
                },
            },
            {
                "type": "business_rule",
                "payload": {"description": "Customer transactions join through accounts."},
            },
        ]


def test_retrieval_pipeline_returns_the_internal_api_contract() -> None:
    response = SemanticRetrievalPipeline(FakeRetrievalService()).run(
        SemanticRetrievalRequest(question="Show customer transactions", conversation=())
    )

    assert response.to_dict() == {
        "status": "Success",
        "context": {
            "tables": ["accounts", "customers"],
            "businessRules": ["Customer transactions join through accounts."],
        },
    }
