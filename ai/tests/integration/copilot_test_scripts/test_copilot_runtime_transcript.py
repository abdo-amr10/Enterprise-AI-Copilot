from tests.integration.copilot_test_scripts.run_integration_scenarios import (
    build_transcript,
)


def test_copilot_runtime_transcript_matches_the_backend_handoff_contract() -> None:
    transcript = build_transcript()

    retrieval, success, rejected = transcript

    assert retrieval["path"] == "/internal/semantic/retrieve"
    assert retrieval["response"]["context"] == {
        "tables": ["Customers", "Sales"],
        "businessRules": ["Active customers have Status = 1."],
    }

    assert success["path"] == "/api/v1/copilot/ask"
    assert success["response"] == {
        "queryId": "req-990",
        "status": "Completed",
        "report": {
            "textSummary": "The total revenue for active customers this month is $145,000.",
            "presentationType": "SummaryCard",
            "data": [{"TotalAmount": 145000.00}],
        },
    }

    assert rejected["response"] == {
        "queryId": "req-991",
        "status": "Failed",
        "errorCode": "SQL_VALIDATION_FAILED",
        "message": "The system could not generate a safe read-only query for this request.",
    }
