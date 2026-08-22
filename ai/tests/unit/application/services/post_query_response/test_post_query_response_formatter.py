import base64

from src.application.dto.backend.copilot.execution_result import BackendExecutionResult
from src.application.services.post_query_response.post_query_response_formatter import PostQueryResponseFormatter
from src.config.post_query_response_settings import PostQueryResponseSettings


class _Exporter:
    content_type = "application/vnd.test.xlsx"
    def export(self, columns, rows):
        assert columns == ("id", "name")
        assert len(rows) == 3
        return b"xlsx-data"


def test_formats_single_values_small_tables_empty_and_backend_failures():
    formatter = PostQueryResponseFormatter(PostQueryResponseSettings(max_inline_rows=2), _Exporter())
    single = formatter.format("q", BackendExecutionResult("Success", ("count",), ((2,),)))
    assert single.presentation_type == "SingleValue"
    assert single.text == "Here’s the information you requested: count is 2."
    assert formatter.format("q", BackendExecutionResult("Success", ("id",), ())).presentation_type == "Empty"
    failed = formatter.format("q", BackendExecutionResult("Failed", error_message="permission denied"))
    assert failed.error_code == "BACKEND_EXECUTION_FAILED"
    assert "permission denied" not in failed.text


def test_large_tables_are_complete_in_memory_excel_payloads():
    formatter = PostQueryResponseFormatter(PostQueryResponseSettings(max_inline_rows=2), _Exporter())
    response = formatter.format("q", BackendExecutionResult("Success", ("id", "name"), ((1, "a"), (2, "b"), (3, "c"))))
    assert response.presentation_type == "Excel"
    assert base64.b64decode(response.file_content_base64) == b"xlsx-data"
    assert response.rows == ()
