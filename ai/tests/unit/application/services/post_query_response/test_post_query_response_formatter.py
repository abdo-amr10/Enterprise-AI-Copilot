import base64

from src.application.dto.backend.copilot.execution_result import BackendExecutionResult
from src.application.services.post_query_response.post_query_response_formatter import (
    PostQueryResponseFormatter,
)
from src.config.post_query_response_settings import PostQueryResponseSettings


class _Exporter:
    content_type = "application/vnd.test.xlsx"

    def export(self, columns, rows):
        assert columns == ("id", "name")
        assert len(rows) == 3
        return b"xlsx-data"


def test_formats_single_values_small_tables_empty_and_backend_failures():
    formatter = PostQueryResponseFormatter(PostQueryResponseSettings(max_inline_rows=2), _Exporter())
    
    # 1. Single value test
    single = formatter.format("q", BackendExecutionResult("Success", ("count",), ((2,),)))
    assert single.presentation_type == "SingleValue"
    assert single.text == "Here’s the information you requested: count is 2."
    assert single.hero_metric is not None
    assert single.hero_metric.label == "COUNT"
    assert single.hero_metric.value == "2"
    assert single.excel_export is None

    # 2. Empty result test
    empty = formatter.format("q", BackendExecutionResult("Success", ("id",), ()))
    assert empty.presentation_type == "Empty"
    assert "couldn’t find" in empty.text
    assert empty.excel_export is None
    assert empty.hero_metric is None


    # 3. Failed backend result test
    failed = formatter.format("q", BackendExecutionResult("Failed", error_message="database timeout"))
    assert failed.presentation_type == "Error"
    assert failed.error_code == "BACKEND_EXECUTION_FAILED"
    assert "timeout" not in failed.text
    assert "SQL" not in failed.text
    assert "query" not in failed.text

    # 4. Permission / RBAC restricted result test
    perm_denied = formatter.format(
        "q",
        BackendExecutionResult("Failed", error_code="PERMISSION_DENIED", error_message="User role lacks salary access"),
    )
    assert perm_denied.presentation_type == "Error"
    assert perm_denied.error_code == "PERMISSION_DENIED"
    assert "permissions" in perm_denied.text
    assert "salary" not in perm_denied.text



def test_multi_row_tables_have_structured_table_and_excel_payloads():
    formatter = PostQueryResponseFormatter(PostQueryResponseSettings(max_inline_rows=2), _Exporter())
    response = formatter.format(
        "q",
        BackendExecutionResult("Success", ("id", "name"), ((1, "a"), (2, "b"), (3, "c"))),
    )
    assert response.presentation_type == "Table"
    assert response.table_data is not None
    assert response.table_data.columns == ("id", "name")
    assert len(response.table_data.rows) == 3
    assert response.excel_export is not None
    assert response.excel_export.available is True
    assert base64.b64decode(response.excel_export.file_content_base64) == b"xlsx-data"

