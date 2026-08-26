from src.application.dto.llm.generation_response import GenerationResponse
from src.application.services.self_correction.sql_critic_service import SQLCriticService


class FakeClient:
    def __init__(self, value): self.value = value
    def generate(self, request):
        if isinstance(self.value, Exception): raise self.value
        return GenerationResponse(self.value)


def test_malformed_critic_response_fails_closed():
    result = SQLCriticService(FakeClient("not json")).evaluate("q", "SELECT 1", "ctx")
    assert result.status == "UNKNOWN"


def test_critic_transport_failure_fails_closed():
    result = SQLCriticService(FakeClient(RuntimeError("offline"))).evaluate("q", "SELECT 1", "ctx")
    assert result.status == "FAIL"
