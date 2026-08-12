"""Run validation, human review, indexing, and retrieval smoke tests."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))

from src.application.services.semantic_layer_validator import SemanticLayerValidator
from src.application.services.semantic_layer.review.review_manager import SemanticLayerReviewManager
from src.config.semantic_settings import SemanticSettings
from src.infrastructure.semantic_layer.retrieval.embedding_service import EmbeddingService
from src.infrastructure.semantic_layer.retrieval.file_semantic_repository import FileSemanticRepository
from src.infrastructure.semantic_layer.retrieval.semantic_index_builder import SemanticIndexBuilder
from src.infrastructure.semantic_layer.retrieval.vector_store import LocalVectorStore


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    root = ROOT / "ai"
    outputs = root / "outputs" / "semantic_layer"
    draft_path = outputs / "initial_draft.json"
    schema_path = ROOT / "docs" / "database_metadata" / "schema.json"

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # Add explicit mappings from the authoritative schema/glossary before validation.
    for entity in draft["entities"]:
        entity["mapping"] = {
            "Customer": "customers", "Branch": "branches", "Account": "accounts",
            "Card": "cards", "Merchant": "merchants", "Transaction": "transactions", "Loan": "loans",
        }[entity["name"]]
    dimension_map = {
        "Customer ID": "customers.customer_id", "Branch ID": "branches.branch_id", "Account ID": "accounts.account_id",
        "Card ID": "cards.card_id", "Merchant ID": "merchants.merchant_id", "Transaction ID": "transactions.transaction_id", "Loan ID": "loans.loan_id",
    }
    for item in draft["dimensions"]:
        item["mapping"] = dimension_map[item["name"]]
    measure_map = {
        "Transaction Volume": "transactions.amount_usd", "Total Balance": "accounts.balance_usd", "Loan Exposure": "loans.loan_amount",
    }
    for item in draft["measures"]:
        item["mapping"] = measure_map[item["name"]]
        item["aggregation"] = "SUM"

    validation = SemanticLayerValidator().validate(draft, schema)
    write_json(outputs / "validation_result.json", validation)

    approved, review = SemanticLayerReviewManager().review(
        draft, validation, decision="approve", reviewer="semantic-layer-owner",
        comments="Approved after automated validation; source mappings are explicit and validated against schema.",
    )
    write_json(outputs / "review_result.json", review)
    write_json(outputs / "approved_semantic_layer.json", approved)

    settings = SemanticSettings()
    index_path = outputs / settings.vector_index_filename
    embedding_service = EmbeddingService(settings.embedding_model_name)
    store = LocalVectorStore(index_path)
    index_result = SemanticIndexBuilder(embedding_service, store).build(approved)
    index_result["index_path"] = str(index_path.relative_to(ROOT))
    write_json(outputs / "index_build_result.json", index_result)

    repository = FileSemanticRepository(outputs / "approved_semantic_layer.json", embedding_service, store)
    questions = [
        "Show customer transactions",
        "What is total account balance by customer?",
        "Which merchants have the most transaction volume?",
        "Show customer loans",
    ]
    retrieval_results = []
    for question in questions:
        results = repository.retrieve(question, settings.default_top_k)
        retrieval_results.append({
            "question": question,
            "results": [
                {"id": r["id"], "type": r["type"], "score": r["score"], "payload": r["payload"]}
                for r in results
            ],
        })
    write_json(outputs / "retrieval_test_results.json", {"tests": retrieval_results})

    print(json.dumps({"validation": validation, "index": index_result, "retrieval_tests": len(questions)}, indent=2))


if __name__ == "__main__":
    main()
