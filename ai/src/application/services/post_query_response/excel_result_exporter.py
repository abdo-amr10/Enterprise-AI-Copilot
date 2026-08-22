"""In-memory XLSX generation for complete large result sets."""

from __future__ import annotations

from io import BytesIO
from typing import Any, Sequence


class ExcelResultExporter:
    """Build an XLSX payload without writing a file on the AI host."""

    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def export(self, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> bytes:
        try:
            import xlsxwriter
        except ImportError as error:
            raise RuntimeError("xlsxwriter is required for large result exports.") from error

        stream = BytesIO()
        workbook = xlsxwriter.Workbook(stream, {"in_memory": True})
        worksheet = workbook.add_worksheet("Results")
        header_format = workbook.add_format({"bold": True, "bg_color": "#D9EAF7"})
        for column_index, name in enumerate(columns):
            worksheet.write(0, column_index, name, header_format)
        for row_index, row in enumerate(rows, start=1):
            for column_index, value in enumerate(row):
                worksheet.write(row_index, column_index, value)
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(rows), max(0, len(columns) - 1))
        workbook.close()
        return stream.getvalue()
