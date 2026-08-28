"""Structured data transfer objects for formatting and presenting copilot query results.

Provides typed representations for narrative summaries, key metrics, tabular grids,
and downloadable spreadsheet exports.
"""


from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HeroMetric:
    """Primary headline metric for visual emphasis in the client."""

    label: str
    value: str
    delta_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize hero metric to camelCase dictionary."""
        result: dict[str, Any] = {
            "label": self.label,
            "value": self.value,
        }
        if self.delta_text is not None:
            result["deltaText"] = self.delta_text
        return result


@dataclass(frozen=True)
class KpiCard:
    """Individual KPI metric card providing concise dimensional insights."""

    label: str
    value: str
    subtext: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize KPI card to camelCase dictionary."""
        result: dict[str, Any] = {
            "label": self.label,
            "value": self.value,
        }
        if self.subtext is not None:
            result["subtext"] = self.subtext
        return result


@dataclass(frozen=True)
class TableData:
    """Structured tabular dataset for in-copilot grid rendering."""

    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    total_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize table dataset to camelCase dictionary."""
        return {
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "totalRows": self.total_rows,
        }


@dataclass(frozen=True)
class ExcelExport:
    """Downloadable OpenXML spreadsheet payload for 1-click client export."""

    available: bool = True
    file_name: str | None = None
    content_type: str | None = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    file_content_base64: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize export metadata to camelCase dictionary."""
        result: dict[str, Any] = {
            "available": self.available,
        }
        if self.file_name:
            result["fileName"] = self.file_name
        if self.content_type:
            result["contentType"] = self.content_type
        if self.file_content_base64:
            result["fileContentBase64"] = self.file_content_base64
        return result


@dataclass(frozen=True)
class PostQueryResponse:
    """Complete adaptive response payload returned by the AI formatting pipeline."""

    status: str
    presentation_type: str
    text: str
    hero_metric: HeroMetric | None = None
    kpi_cards: tuple[KpiCard, ...] | None = None
    table_data: TableData | None = None
    excel_export: ExcelExport | None = None
    error_code: str | None = None

    # Backward-compatible accessors
    @property
    def columns(self) -> tuple[str, ...]:
        """Return columns from table_data if present."""
        return self.table_data.columns if self.table_data else ()

    @property
    def rows(self) -> tuple[tuple[Any, ...], ...]:
        """Return rows from table_data if present."""
        return self.table_data.rows if self.table_data else ()

    @property
    def row_count(self) -> int:
        """Return total row count from table_data if present."""
        return self.table_data.total_rows if self.table_data else 0

    @property
    def file_name(self) -> str | None:
        """Return file name from excel_export if present."""
        return self.excel_export.file_name if self.excel_export else None

    @property
    def content_type(self) -> str | None:
        """Return content type from excel_export if present."""
        return self.excel_export.content_type if self.excel_export else None

    @property
    def file_content_base64(self) -> str | None:
        """Return base64 content from excel_export if present."""
        return self.excel_export.file_content_base64 if self.excel_export else None

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete response to camelCase dictionary matching backend contract."""
        result: dict[str, Any] = {
            "status": self.status,
            "presentationType": self.presentation_type,
            "text": self.text,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "rowCount": self.row_count,
        }
        if self.hero_metric is not None:
            result["heroMetric"] = self.hero_metric.to_dict()
        else:
            result["heroMetric"] = None

        if self.kpi_cards is not None:
            result["kpiCards"] = [card.to_dict() for card in self.kpi_cards]
        else:
            result["kpiCards"] = None

        if self.table_data is not None:
            result["tableData"] = self.table_data.to_dict()
        else:
            result["tableData"] = None

        if self.excel_export is not None:
            result["excelExport"] = self.excel_export.to_dict()
            if self.excel_export.file_name:
                result["fileName"] = self.excel_export.file_name
                result["contentType"] = self.excel_export.content_type
                result["fileContentBase64"] = self.excel_export.file_content_base64
        else:
            result["excelExport"] = None

        if self.error_code:
            result["errorCode"] = self.error_code

        return result

