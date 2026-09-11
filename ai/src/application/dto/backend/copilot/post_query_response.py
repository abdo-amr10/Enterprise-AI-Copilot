"""Structured data transfer objects for formatting and presenting copilot query results.

Provides Pydantic-validated models for narrative summaries, key metrics, tabular grids,
and downloadable spreadsheet exports.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictBaseModel(BaseModel):
    """Base Pydantic model with strict settings and alias population support."""

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        validate_assignment=True,
        protected_namespaces=(),
    )


class HeroMetric(StrictBaseModel):
    """Primary headline metric for visual emphasis in the client."""

    label: str
    value: str
    delta_text: str | None = Field(default=None, alias="deltaText")

    def to_dict(self) -> dict[str, Any]:
        """Serialize hero metric to camelCase dictionary."""
        result: dict[str, Any] = {
            "label": self.label,
            "value": self.value,
        }
        if self.delta_text is not None:
            result["deltaText"] = self.delta_text
        return result


class KpiCard(StrictBaseModel):
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


class TableData(StrictBaseModel):
    """Structured tabular dataset for in-copilot grid rendering."""

    columns: tuple[str, ...] = Field(default_factory=tuple)
    rows: tuple[tuple[Any, ...], ...] = Field(default_factory=tuple)
    total_rows: int = Field(default=0, alias="totalRows")

    def to_dict(self) -> dict[str, Any]:
        """Serialize table dataset to camelCase dictionary."""
        return {
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "totalRows": self.total_rows,
        }


class ExcelExport(StrictBaseModel):
    """Downloadable OpenXML spreadsheet payload for 1-click client export."""

    available: bool = True
    file_name: str | None = Field(default=None, alias="fileName")
    content_type: str | None = Field(
        default="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        alias="contentType",
    )
    file_content_base64: str | None = Field(default=None, alias="fileContentBase64")

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


class PostQueryResponse(StrictBaseModel):
    """Complete adaptive response payload returned by the AI formatting pipeline."""

    status: str
    presentation_type: str = Field(alias="presentationType")
    text: str
    hero_metric: HeroMetric | None = Field(default=None, alias="heroMetric")
    kpi_cards: tuple[KpiCard, ...] | None = Field(default=None, alias="kpiCards")
    table_data: TableData | None = Field(default=None, alias="tableData")
    excel_export: ExcelExport | None = Field(default=None, alias="excelExport")
    error_code: str | None = Field(default=None, alias="errorCode")

    # Backward-compatible flat fields
    columns: tuple[str, ...] = Field(default_factory=tuple)
    rows: tuple[tuple[Any, ...], ...] = Field(default_factory=tuple)
    row_count: int = Field(default=0, alias="rowCount")
    file_name: str | None = Field(default=None, alias="fileName")
    content_type: str | None = Field(default=None, alias="contentType")
    file_content_base64: str | None = Field(default=None, alias="fileContentBase64")

    @model_validator(mode="after")
    def _sync_backward_compatible_fields(self) -> PostQueryResponse:
        """Synchronize flat backward-compatible fields with table_data and excel_export."""
        if self.table_data is not None:
            if not self.columns and self.table_data.columns:
                object.__setattr__(self, "columns", tuple(self.table_data.columns))
            if not self.rows and self.table_data.rows:
                object.__setattr__(self, "rows", tuple(self.table_data.rows))
            if self.row_count == 0 and self.table_data.total_rows != 0:
                object.__setattr__(self, "row_count", self.table_data.total_rows)

        if self.excel_export is not None:
            if self.file_name is None and self.excel_export.file_name:
                object.__setattr__(self, "file_name", self.excel_export.file_name)
            if self.content_type is None and self.excel_export.content_type:
                object.__setattr__(self, "content_type", self.excel_export.content_type)
            if self.file_content_base64 is None and self.excel_export.file_content_base64:
                object.__setattr__(
                    self, "file_content_base64", self.excel_export.file_content_base64
                )

        return self

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

