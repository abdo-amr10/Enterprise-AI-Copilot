import json
import os
import sys

# Ensure ai dir is in path
ai_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../"))
sys.path.insert(0, ai_dir)

from fastapi.testclient import TestClient
from main import app
from src.api.post_query_dependencies import get_post_query_response_formatter
from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.config.post_query_response_settings import PostQueryResponseSettings

# Ensure utf-8 encoding for standard output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Override with deterministic formatter so demo runs immediately without external Ollama dependency
app.dependency_overrides[get_post_query_response_formatter] = lambda: PostQueryResponseFormatter(
    settings=PostQueryResponseSettings(max_inline_rows=100)
)

client = TestClient(app)

def run_test(scenario_name: str, payload: dict):
    print("\n" + "=" * 80)
    print(f">> {scenario_name}")
    print("=" * 80)
    print("[SENT TO AI FORMATTER]:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    response = client.post("/internal/copilot/format-execution-result", json=payload)
    
    print("\n[RECEIVED RESPONSE FROM AI]:")
    print(f"HTTP Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # 1. Financial / Numeric Query (Hero + KPI Cards + Table + Excel)
    run_test(
        "1. Financial & Numeric Query (Hero + KPI Cards + Table + Excel)",
        {
            "question": "What is the quarterly revenue and transaction volume for regional branches in Q1 and Q2?",
            "executionResult": [
                {"BranchName": "Cairo Downtown", "Quarter": "Q1", "Revenue": 450000.0, "TransactionCount": 1200},
                {"BranchName": "Cairo Downtown", "Quarter": "Q2", "Revenue": 520000.0, "TransactionCount": 1350},
                {"BranchName": "Alexandria Port", "Quarter": "Q1", "Revenue": 310000.0, "TransactionCount": 890},
                {"BranchName": "Alexandria Port", "Quarter": "Q2", "Revenue": 340000.0, "TransactionCount": 940}
            ]
        }
    )

    # 2. Text / Categorical List Query (No Hero, No KPIs, Table + Excel only)
    run_test(
        "2. Text & Categorical List Query (Text List - Hero and KPIs are null)",
        {
            "question": "List all active system administrators",
            "executionResult": [
                {"Username": "jdoe", "Email": "jdoe@company.com", "Department": "IT Infrastructure", "Role": "Admin"},
                {"Username": "asmith", "Email": "asmith@company.com", "Department": "Security", "Role": "Auditor"},
                {"Username": "rchen", "Email": "rchen@company.com", "Department": "IT Ops", "Role": "Admin"}
            ]
        }
    )

    # 3. Single Value Query (SingleValue - No Table, No Excel)
    run_test(
        "3. Single Value / Scalar Query (Single Value - No Table, No Excel)",
        {
            "question": "What is the total number of registered customers?",
            "executionResult": [
                {"TotalCustomers": 4520}
            ]
        }
    )

    # 4. Empty Result Query (Empty - No Table, No Excel, No Hero, No KPIs)
    run_test(
        "4. Empty Result (0 rows)",
        {
            "question": "Find transactions with amount greater than $1,000,000",
            "executionResult": []
        }
    )
