"""Deterministic Result Resolver operating on previous execution results.

Evaluates questions deterministically without calling LLMs, without Text-to-SQL,
and without SQL generation. Never hallucinates information absent from the result.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from src.application.services.conversation.normalization.normalizer import RequestNormalizer
from src.application.services.conversation.result_resolution.models import (
    ResultResolutionOutcome,
    ResultResolutionStatus,
)
from src.application.services.conversation.state.conversation_state import ResultMetadata

logger = logging.getLogger(__name__)


class ResultResolver:
    """Answers follow-up questions directly from prior query result data or summary."""

    _ORDINAL_WORDS = {
        "first": 1,
        "1st": 1,
        "second": 2,
        "2nd": 2,
        "third": 3,
        "3rd": 3,
        "fourth": 4,
        "4th": 4,
        "fifth": 5,
        "5th": 5,
        "sixth": 6,
        "6th": 6,
        "seventh": 7,
        "7th": 7,
        "eighth": 8,
        "8th": 8,
        "ninth": 9,
        "9th": 9,
        "tenth": 10,
        "10th": 10,
    }

    _ORDINAL_PATTERN = re.compile(
        r"\b(?:who|what|which)(?:\s+one)?\s+is\s+(?:#|number|no\.?|num\.?)?\s*(\d+)\b|"
        r"\b(?:number|#|no\.?)\s*(\d+)\b|"
        r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)\b",
        re.IGNORECASE,
    )

    _COUNT_PATTERN = re.compile(
        r"\b(?:how\s+many(?:\s+(?:rows|records|items|results|customers|employees))?|count|total\s+rows)\b",
        re.IGNORECASE,
    )

    _EXTREME_PATTERN = re.compile(
        r"\b(?:which|who|what)(?:\s+[a-zA-Z_]+)?\s+(?:is|has|was|had)?\s*(?:the\s+)?(highest|maximum|max|top|lowest|minimum|min)\b",
        re.IGNORECASE,
    )

    def resolve(
        self,
        question: str,
        result_metadata: Optional[ResultMetadata],
        *,
        summary: Optional[str] = None,
        current_tenant_id: Optional[str] = None,
        current_user_id: Optional[str] = None,
    ) -> ResultResolutionOutcome:
        """Resolve question against previous result metadata and summary."""
        if result_metadata is None and not summary:
            return ResultResolutionOutcome.invalid_reference("No previous result available to answer from.")

        # Security context validation: ensure previous result was produced in a compatible security scope
        if result_metadata is not None:
            if result_metadata.tenant_id and (not current_tenant_id or result_metadata.tenant_id != current_tenant_id):
                return ResultResolutionOutcome.not_answerable("Security tenant scope mismatch with previous result.")
            if result_metadata.user_id and (not current_user_id or result_metadata.user_id != current_user_id):
                return ResultResolutionOutcome.not_answerable("Security user authorization mismatch with previous result.")

        norm_q = RequestNormalizer.normalize(question)

        # 1. Count / Row count queries
        if self._COUNT_PATTERN.search(norm_q):
            if result_metadata and result_metadata.row_count is not None:
                return ResultResolutionOutcome.answerable(
                    f"There are {result_metadata.row_count} rows in the previous result.",
                    confidence=1.0,
                )

        # 2. Ordinal / Rank queries (e.g. "Who is #3?", "What is the 3rd one?")
        ordinal_match = self._ORDINAL_PATTERN.search(norm_q)
        if ordinal_match:
            rank = None
            if ordinal_match.group(1):
                rank = int(ordinal_match.group(1))
            elif ordinal_match.group(2):
                rank = int(ordinal_match.group(2))
            elif ordinal_match.group(3):
                rank = self._ORDINAL_WORDS.get(ordinal_match.group(3).lower())

            if rank is not None and rank > 0:
                if not result_metadata or not result_metadata.sample_rows:
                    return ResultResolutionOutcome.not_answerable("Result rows are not available for rank lookup.")

                index = rank - 1
                if 0 <= index < len(result_metadata.sample_rows):
                    row = result_metadata.sample_rows[index]
                    cols = result_metadata.columns
                    if cols and len(cols) == len(row):
                        row_details = ", ".join(f"{c}: {v}" for c, v in zip(cols, row) if v is not None)
                        # If primary name column exists, format nicely
                        answer = f"Number {rank} is {row[0]} ({row_details})" if len(row) > 1 else f"Number {rank} is {row[0]}"
                    else:
                        answer = f"Number {rank} is {row[0] if len(row) > 0 else 'empty'}"
                    return ResultResolutionOutcome.answerable(answer, row_index=index)
                else:
                    return ResultResolutionOutcome.not_answerable(
                        f"Rank {rank} is out of range for result with {result_metadata.row_count} rows."
                    )

        # 3. Min/Max Extreme queries (e.g. "Which region is highest?")
        extreme_match = self._EXTREME_PATTERN.search(norm_q)
        if extreme_match and result_metadata and result_metadata.sample_rows:
            is_max = extreme_match.group(1).lower() in ("highest", "maximum", "max", "top")
            cols = result_metadata.columns
            rows = result_metadata.sample_rows

            # Find numeric columns and categorical columns
            numeric_col_idx = None
            cat_col_idx = None

            for i, col in enumerate(cols):
                # Check sample row values
                val = rows[0][i] if len(rows[0]) > i else None
                if isinstance(val, (int, float)) or (isinstance(val, str) and val.replace(".", "", 1).replace("-", "", 1).isdigit()):
                    if numeric_col_idx is None:
                        numeric_col_idx = i
                else:
                    if cat_col_idx is None:
                        cat_col_idx = i

            if numeric_col_idx is not None and cat_col_idx is not None:
                def extract_num(r):
                    try:
                        return float(r[numeric_col_idx])
                    except (ValueError, TypeError):
                        return float("-inf") if is_max else float("inf")

                best_row = max(rows, key=extract_num) if is_max else min(rows, key=extract_num)
                best_cat = best_row[cat_col_idx]
                best_val = best_row[numeric_col_idx]
                metric_name = cols[numeric_col_idx]
                adjective = "highest" if is_max else "lowest"
                answer = f"{best_cat} has the {adjective} {metric_name} ({best_val})."
                return ResultResolutionOutcome.answerable(answer, column=cols[cat_col_idx])

        # 4. Cell / Attribute lookup (e.g. "What department is Sara in?", "What was Sara's salary?")
        if result_metadata and result_metadata.columns and result_metadata.sample_rows:
            cols = [c.lower() for c in result_metadata.columns]
            rows = result_metadata.sample_rows

            # Identify target column requested (e.g. department, salary, role, status, email, phone)
            target_col_idx = None
            target_col_name = None
            for i, col_name in enumerate(cols):
                if re.search(r"\b" + re.escape(col_name) + r"\b", norm_q):
                    target_col_idx = i
                    target_col_name = result_metadata.columns[i]
                    break

            # Identify target row by matching any string cell value against query words
            target_row_idx = None
            for row_idx, row in enumerate(rows):
                for cell_idx, cell in enumerate(row):
                    if cell is not None and isinstance(cell, str) and len(cell.strip()) >= 2:
                        cell_clean = cell.strip().lower()
                        if re.search(r"\b" + re.escape(cell_clean) + r"\b", norm_q):
                            target_row_idx = row_idx
                            break
                if target_row_idx is not None:
                    break

            if target_row_idx is not None and target_col_idx is not None:
                cell_value = rows[target_row_idx][target_col_idx]
                return ResultResolutionOutcome.answerable(
                    str(cell_value),
                    column=target_col_name,
                    row_index=target_row_idx,
                )

            # CRITICAL SAFETY: If the user explicitly asks for a field (e.g., "department")
            # and a subject is found, but the field is NOT present in columns:
            # We MUST return NOT_ANSWERABLE so we never hallucinate!
            if target_row_idx is not None and target_col_idx is None:
                # User asked about an entity in the table, but the requested attribute is missing
                return ResultResolutionOutcome.not_answerable(
                    "Target entity found in result, but requested attribute column is not present."
                )

        # 5. Text Summary Lookup (e.g. "Egypt: $2.5M, Brazil: $1.1M" -> "What was the sales amount for Egypt?")
        eff_summary = summary or (result_metadata.summary if result_metadata else None)
        if eff_summary:
            # Extract pattern: entity followed by colon/dash and value
            # e.g., "Egypt's total sales were $2.5M" or "Egypt: $2.5M"
            words = [w for w in re.split(r"[\s,;?.'\"]+", norm_q) if len(w) > 3]
            for w in words:
                # Look for word in summary
                pattern = re.compile(
                    r"\b" + re.escape(w) + r"[\'\w]*\s*(?::|was|were|totaled|is|=)\s*([^\n,;.]+)",
                    re.IGNORECASE,
                )
                match = pattern.search(eff_summary)
                if match:
                    val = match.group(1).strip()
                    return ResultResolutionOutcome.answerable(
                        f"{w.title()}'s value was {val}.",
                        confidence=0.9,
                    )

        return ResultResolutionOutcome.not_answerable("Question cannot be answered directly from the previous result.")
