"""Executive business narrative generation and deterministic metric extraction for execution results.

Provides mathematical extraction of summary metrics and natural-language narrative synthesis.
"""


from __future__ import annotations

import json
from typing import Any, Sequence

from src.application.dto.backend.copilot.post_query_response import HeroMetric, KpiCard
from src.application.dto.llm.generation_request import GenerationRequest
from src.application.ports.llm_client import LLMClient
from src.prompts.post_query_response_summary_prompt import (
    POST_QUERY_RESPONSE_SUMMARY_PROMPT,
)


class PostQueryResponseSummarizer:
    """Produces natural business narratives and deterministic metric extractions."""

    def __init__(self, llm_client: LLMClient, max_sample_rows: int = 5) -> None:
        self._llm_client = llm_client
        self._max_sample_rows = max_sample_rows

    def summarize(
        self,
        question: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
        row_count: int,
        presentation_type: str,
    ) -> str:
        """Generate a concise, human-friendly executive business narrative."""
        stats = self._statistics(columns, rows)
        context = {
            "presentationType": presentation_type,
            "row_count": row_count,
            "columns": list(columns),
            "sample_rows": [list(row) for row in rows[: self._max_sample_rows]],
            "available_statistics": stats,
        }
        prompt = POST_QUERY_RESPONSE_SUMMARY_PROMPT.format(
            question=question,
            context=json.dumps(context, default=str, ensure_ascii=False),
        )

        try:
            text = self._llm_client.generate(GenerationRequest(prompt=prompt)).text.strip()
            if not text:
                return self._fallback_narrative(row_count, stats)
            return text
        except Exception:
            return self._fallback_narrative(row_count, stats)

    def extract_metrics(
        self,
        columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
    ) -> tuple[HeroMetric | None, tuple[KpiCard, ...] | None]:
        """Extract HeroMetric and KpiCard items deterministically only if meaningful numeric metrics exist."""
        if not columns or not rows:
            return None, None

        stats = self._statistics(columns, rows)
        numeric_stats = stats.get("numeric", {})

        # If no numeric columns exist, this is a categorical/textual dataset -> return None
        if not numeric_stats:
            return None, None

        # Determine dominant numeric column (prioritize currency/amount/revenue/total keywords, else first)
        dominant_col = self._pick_dominant_numeric_column(list(numeric_stats.keys()))
        dom_stat = numeric_stats[dominant_col]

        # 1. Build Hero Metric
        hero_val_formatted = self._format_numeric_value(dominant_col, dom_stat["sum"] if len(rows) > 1 else dom_stat["max"])
        hero_label = f"TOTAL {dominant_col.upper()}" if len(rows) > 1 else dominant_col.upper()
        hero_metric = HeroMetric(
            label=hero_label,
            value=hero_val_formatted,
            delta_text=f"Aggregated across {len(rows)} record(s)" if len(rows) > 1 else None,
        )

        # 2. Build KPI Cards (up to 4 cards)
        cards: list[KpiCard] = []

        # Card 1: Total volume of dominant column
        cards.append(
            KpiCard(
                label=f"TOTAL {dominant_col.upper()}",
                value=self._format_numeric_value(dominant_col, dom_stat["sum"]),
                subtext=f"Sum of {len(rows)} entries",
            )
        )

        # Card 2: Record Count
        cards.append(
            KpiCard(
                label="TOTAL RECORDS",
                value=f"{len(rows):,}",
                subtext="Total count",
            )
        )

        # Card 3: Average
        cards.append(
            KpiCard(
                label=f"AVG {dominant_col.upper()}",
                value=self._format_numeric_value(dominant_col, dom_stat["average"]),
                subtext="Mean per record",
            )
        )

        # Card 4: Secondary numeric column or Peak Maximum
        other_cols = [c for c in numeric_stats if c != dominant_col]
        if other_cols:
            sec_col = other_cols[0]
            sec_stat = numeric_stats[sec_col]
            cards.append(
                KpiCard(
                    label=f"TOTAL {sec_col.upper()}",
                    value=self._format_numeric_value(sec_col, sec_stat["sum"]),
                    subtext=f"Secondary metric",
                )
            )
        else:
            cards.append(
                KpiCard(
                    label=f"MAX {dominant_col.upper()}",
                    value=self._format_numeric_value(dominant_col, dom_stat["max"]),
                    subtext=f"Peak value in dataset",
                )
            )

        return hero_metric, tuple(cards)

    @staticmethod
    def _statistics(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> dict[str, Any]:
        """Return deterministic statistics calculated from the supplied result."""
        result: dict[str, Any] = {"non_null_counts": {}}
        for index, column in enumerate(columns):
            values = [
                row[index] for row in rows if len(row) > index and row[index] is not None
            ]
            result["non_null_counts"][column] = len(values)
            numeric = [
                value
                for value in values
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            ]
            if numeric:
                result.setdefault("numeric", {})[column] = {
                    "min": min(numeric),
                    "max": max(numeric),
                    "sum": sum(numeric),
                    "average": sum(numeric) / len(numeric),
                }
        return result

    @staticmethod
    def _pick_dominant_numeric_column(numeric_columns: list[str]) -> str:
        """Identify the most significant numeric metric column based on business keywords."""
        keywords = ["revenue", "amount", "spend", "sales", "total", "price", "balance", "cost", "profit"]
        for kw in keywords:
            for col in numeric_columns:
                if kw in col.lower():
                    return col
        return numeric_columns[0]

    @staticmethod
    def _format_numeric_value(column_name: str, value: float | int) -> str:
        """Format numbers with appropriate currency symbols and thousands separators."""
        is_currency = any(
            kw in column_name.lower()
            for kw in ["revenue", "amount", "spend", "sales", "price", "balance", "cost", "profit", "salary"]
        )
        if is_currency:
            if isinstance(value, float) and value % 1 != 0:
                return f"${value:,.2f}"
            return f"${value:,.0f}"
        if isinstance(value, float) and value % 1 != 0:
            return f"{value:,.2f}"
        return f"{int(value):,}"

    @staticmethod
    def _fallback_narrative(row_count: int, stats: dict[str, Any]) -> str:
        """Provide a clean, business-oriented fallback text without technical jargon."""
        if row_count == 0:
            return "I couldn’t find any matching information in the system for your request."
        if row_count == 1:
            return "Here is the information you requested."
        numeric = stats.get("numeric", {})
        if numeric:
            first_col = next(iter(numeric))
            total_val = numeric[first_col]["sum"]
            return f"Here is the breakdown across {row_count:,} records with a consolidated {first_col} of {total_val:,.2f}."
        return f"Here is the requested information across {row_count:,} records."


