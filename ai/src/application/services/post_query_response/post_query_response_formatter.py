"""Deterministic formatting and adaptive routing of backend execution results.

Orchestrates the assembly of narrative summaries, hero metrics, KPI cards,
tabular data, and spreadsheet exports based on result structure and permissions.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone

from src.application.dto.backend.copilot.execution_result import BackendExecutionResult
from src.application.dto.backend.copilot.post_query_response import (
    ExcelExport,
    HeroMetric,
    KpiCard,
    PostQueryResponse,
    TableData,
)
from src.application.services.post_query_response.excel_result_exporter import (
    ExcelResultExporter,
)
from src.application.services.post_query_response.post_query_response_summarizer import (
    PostQueryResponseSummarizer,
)
from src.config.post_query_response_settings import PostQueryResponseSettings


class PostQueryResponseFormatter:
    """Classifies execution results and adaptively constructs structured copilot intelligence."""

    def __init__(
        self,
        settings: PostQueryResponseSettings | None = None,
        excel_exporter: ExcelResultExporter | None = None,
        summarizer: PostQueryResponseSummarizer | None = None,
    ) -> None:
        self._settings = settings or PostQueryResponseSettings()
        self._excel_exporter = excel_exporter or ExcelResultExporter()
        self._summarizer = summarizer

    def format(self, question: str, result: BackendExecutionResult) -> PostQueryResponse:
        """Format an execution result into an adaptive, business-oriented PostQueryResponse."""
        # 1. Error / Failed State (including Permissions & Role-based Access Control)
        if result.status == "Failed":
            err_code = (result.error_code or "").upper()
            err_msg = (result.error_message or "").lower()
            
            is_permission_issue = any(
                term in err_code for term in ["PERMISSION", "UNAUTHORIZED", "FORBIDDEN", "ACCESS_DENIED", "ROLE"]
            ) or any(
                term in err_msg for term in ["permission", "authorized", "forbidden", "access denied", "not allowed"]
            )
            
            if is_permission_issue:
                text = "You do not have the required permissions to view this information. Please contact your administrator if you need access."
                error_code = result.error_code or "PERMISSION_DENIED"
            else:
                text = "I was unable to complete your request right now. Please try again or rephrase."
                error_code = result.error_code or "BACKEND_EXECUTION_FAILED"

            return PostQueryResponse(
                status="Failed",
                presentation_type="Error",
                text=text,
                error_code=error_code,
            )


        # 2. Empty Result State (0 rows)
        if result.effective_row_count == 0:
            default_text = "I couldn’t find any information matching that in the system."
            narrative = self._generate_narrative(
                question, result, "Empty", default_text
            )
            return PostQueryResponse(
                status="Success",
                presentation_type="Empty",
                text=narrative,
                hero_metric=None,
                kpi_cards=None,
                table_data=TableData(columns=result.columns, rows=(), total_rows=0),
                excel_export=None,
            )


        # 3. Single Value / Scalar Result State (1 row, 1 column)
        if len(result.columns) == 1 and result.effective_row_count == 1:
            val = result.rows[0][0]
            col_name = result.columns[0]
            hero = HeroMetric(label=col_name.upper(), value=str(val))
            default_text = f"Here’s the information you requested: {col_name} is {val}."
            
            narrative = self._generate_narrative(
                question, result, "SingleValue", default_text
            )
            return PostQueryResponse(
                status="Success",
                presentation_type="SingleValue",
                text=narrative,
                hero_metric=hero,
                kpi_cards=None,
                table_data=TableData(columns=result.columns, rows=result.rows, total_rows=1),
                excel_export=None,
            )


        # 4. Multi-Row Tabular Result State (Hybrid: Narrative + Grid + Conditional KPIs & Excel)
        return self._format_hybrid_table(question, result)

    def _format_hybrid_table(
        self, question: str, result: BackendExecutionResult
    ) -> PostQueryResponse:
        """Construct a comprehensive Hybrid response with data table, optional KPIs, and Excel export."""
        # Extract metrics (Hero & KPI cards) deterministically if numeric columns exist
        hero_metric: HeroMetric | None = None
        kpi_cards: tuple[KpiCard, ...] | None = None

        if self._summarizer is not None:
            hero_metric, kpi_cards = self._summarizer.extract_metrics(
                result.columns, result.rows
            )
        else:
            hero_metric, kpi_cards = PostQueryResponseSummarizer._extract_static_metrics(
                result.columns, result.rows
            ) if hasattr(PostQueryResponseSummarizer, "_extract_static_metrics") else (None, None)

        # Generate downloadable Excel OpenXML spreadsheet payload
        excel_export = self._build_excel_export(result)

        # Build Table Data
        table_data = TableData(
            columns=result.columns,
            rows=result.rows,
            total_rows=result.effective_row_count,
        )

        # Determine presentation type label (Table or Hybrid)
        presentation_type = "Table"

        default_text = (
            f"Found {result.effective_row_count:,} matching records for your request."
        )
        narrative = self._generate_narrative(
            question, result, presentation_type, default_text
        )

        return PostQueryResponse(
            status="Success",
            presentation_type=presentation_type,
            text=narrative,
            hero_metric=hero_metric,
            kpi_cards=kpi_cards,
            table_data=table_data,
            excel_export=excel_export,
        )

    def _build_excel_export(self, result: BackendExecutionResult) -> ExcelExport | None:
        """Create in-memory Excel file export if rows and columns exist."""
        if result.effective_row_count == 0 or not result.columns:
            return None

        payload = self._excel_exporter.export(result.columns, result.rows)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return ExcelExport(
            available=True,
            file_name=f"copilot-results-{timestamp}.xlsx",
            content_type=self._excel_exporter.content_type,
            file_content_base64=base64.b64encode(payload).decode("ascii"),
        )

    def _generate_narrative(
        self,
        question: str,
        result: BackendExecutionResult,
        presentation_type: str,
        fallback_text: str,
    ) -> str:
        """Generate executive narrative via LLM with safe fallback on error."""
        if self._summarizer is None:
            return fallback_text
        try:
            return self._summarizer.summarize(
                question,
                result.columns,
                result.rows,
                result.effective_row_count,
                presentation_type,
            )
        except Exception:
            return fallback_text

