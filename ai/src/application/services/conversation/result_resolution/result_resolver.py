"""Deterministic result resolution for follow-up queries answerable from existing data."""

from __future__ import annotations

import logging
import re
from typing import Optional

from src.application.services.conversation.normalization.normalizer import (
    RequestNormalizer,
)
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
        r"\b(?:who|what|which)(?:\s+is|\s+was)?\s+(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)(?:\s+(?:one|row|item|record|result))?\b|"
        r"\b(?:the\s+)?(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|sixth|6th|seventh|7th|eighth|8th|ninth|9th|tenth|10th)\s+(?:one|row|item|record|result)\b|"
        r"^(?:#|number|no\.?)\s*(\d+)\??$",
        re.IGNORECASE,
    )

    _COUNT_PATTERN = re.compile(
        r"\b(?:how\s+many(?:\s+[a-zA-Z_]+)?|count|total\s+rows)\b",
        re.IGNORECASE,
    )

    _EXTREME_PATTERN = re.compile(
        r"\b(?:which|who|what)(?:\s+[a-zA-Z_]+)?\s+(?:is|has|was|had)?\s*(?:the\s+)?(highest|maximum|max|top|lowest|minimum|min)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_column_tokens_and_phrases(col_name: str) -> tuple[str, str, list[str]]:
        """Return (clean, spaced, tokens) for a column name handling CamelCase and delimiters."""
        col_clean = col_name.lower()
        col_spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", col_name).lower()
        tokens = [t for t in re.split(r"[_\s\-]+", col_spaced) if len(t) > 2]
        return col_clean, col_spaced, tokens

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
        count_match = self._COUNT_PATTERN.search(norm_q)
        if count_match:
            specific_noun_match = re.search(r"\bhow\s+many\s+([a-zA-Z_]+)\b", norm_q)
            is_generic_count = True
            if specific_noun_match:
                noun = specific_noun_match.group(1).lower()
                generic_nouns = {
                    "rows", "records", "items", "results", "entries", "people", "ones",
                    "of", "are", "were", "is", "there", "total",
                }
                if noun not in generic_nouns:
                    cols_str = " ".join(c.lower() for c in (result_metadata.columns if result_metadata else []))
                    if noun not in cols_str and noun.rstrip("s") not in cols_str:
                        is_generic_count = False

            if is_generic_count and result_metadata and result_metadata.row_count is not None:
                return ResultResolutionOutcome.answerable(
                    f"There are {result_metadata.row_count} rows in the previous result.",
                    confidence=1.0,
                )

        # 2. Ordinal / Rank queries (e.g. "Who is #3?", "What is the 3rd one?")
        is_limit_query = bool(re.search(r"\b(?:first|top|last)\s+\d+\b", norm_q))
        if not is_limit_query:
            ordinal_match = self._ORDINAL_PATTERN.search(norm_q)
            if ordinal_match:
                rank = None
                groups = ordinal_match.groups()
                if groups[0]:
                    rank = int(groups[0])
                elif groups[1]:
                    rank = self._ORDINAL_WORDS.get(groups[1].lower())
                elif groups[2]:
                    rank = self._ORDINAL_WORDS.get(groups[2].lower())
                elif groups[3]:
                    rank = int(groups[3])

                if rank is not None and rank > 0:
                    if not result_metadata or not result_metadata.sample_rows:
                        return ResultResolutionOutcome.not_answerable("Result rows are not available for rank lookup.")

                    index = rank - 1
                    if 0 <= index < len(result_metadata.sample_rows):
                        row = result_metadata.sample_rows[index]
                        cols = result_metadata.columns
                        if cols and len(cols) == len(row):
                            row_details = ", ".join(f"{c}: {v}" for c, v in zip(cols, row) if v is not None)
                            answer = f"Number {rank} is {row[0]} ({row_details})" if len(row) > 1 else f"Number {rank} is {row[0]}"
                        else:
                            answer = f"Number {rank} is {row[0] if len(row) > 0 else 'empty'}"
                        return ResultResolutionOutcome.answerable(answer, row_index=index)
                    else:
                        return ResultResolutionOutcome.not_answerable(
                            f"Rank {rank} is out of range for result with {result_metadata.row_count} rows."
                        )

        # 3. Min/Max Extreme queries (e.g. "Which region is highest?", "Which customer has the highest balance?")
        extreme_match = self._EXTREME_PATTERN.search(norm_q)
        if extreme_match and result_metadata and result_metadata.sample_rows:
            is_max = True
            if extreme_match.group(1):
                is_max = extreme_match.group(1).lower() in ("highest", "maximum", "max", "top")

            cols = result_metadata.columns
            rows = result_metadata.sample_rows

            metric_match = re.search(
                r"\b(?:highest|maximum|max|top|lowest|minimum|min)\s+([a-zA-Z_]+)\b",
                norm_q,
                re.IGNORECASE,
            )
            requested_metric = None
            if metric_match:
                raw_m = metric_match.group(1)
                if raw_m:
                    raw_m = raw_m.strip().lower()
                    if raw_m not in {"one", "result", "record", "row", "value", "number", "of"}:
                        requested_metric = raw_m

            # Find all numeric columns and categorical columns
            numeric_col_indices = []
            cat_col_indices = []

            for i, col in enumerate(cols):
                val = rows[0][i] if len(rows[0]) > i else None
                is_num = isinstance(val, (int, float)) or (
                    isinstance(val, str) and val.replace(".", "", 1).replace("-", "", 1).isdigit()
                )
                if is_num:
                    numeric_col_indices.append(i)
                else:
                    cat_col_indices.append(i)

            target_num_col_idx = None

            # If requested_metric was not extracted from "highest/lowest <word>",
            # check if any numeric column name, spaced phrase, or token appears in the query
            if requested_metric is None:
                for i in numeric_col_indices:
                    col = cols[i]
                    col_clean, col_spaced, tokens = self._extract_column_tokens_and_phrases(col)
                    if (
                        re.search(r"\b" + re.escape(col_clean) + r"\b", norm_q, re.IGNORECASE)
                        or re.search(r"\b" + re.escape(col_spaced) + r"\b", norm_q, re.IGNORECASE)
                    ):
                        requested_metric = col_clean
                        target_num_col_idx = i
                        break
                    for token in tokens:
                        if re.search(r"\b" + re.escape(token) + r"\b", norm_q, re.IGNORECASE):
                            requested_metric = token
                            target_num_col_idx = i
                            break
                    if target_num_col_idx is not None:
                        break

            # Find matching numeric column index if requested_metric was explicitly extracted
            if requested_metric and target_num_col_idx is None:
                for i in numeric_col_indices:
                    col = cols[i]
                    col_clean, col_spaced, tokens = self._extract_column_tokens_and_phrases(col)
                    if (
                        requested_metric == col_clean
                        or requested_metric == col_spaced
                        or requested_metric in tokens
                        or requested_metric in col_clean
                        or requested_metric in col_spaced
                        or col_clean in requested_metric
                    ):
                        target_num_col_idx = i
                        break
                # If an explicit metric was asked for but not found in columns, DO NOT HALLUCINATE!
                if target_num_col_idx is None:
                    return ResultResolutionOutcome.not_answerable(
                        f"Requested metric '{requested_metric}' is not present in previous result columns."
                    )

            # CRITICAL AUDIT RISK #2: Multi-Numeric Column Ambiguity
            if target_num_col_idx is None:
                if len(numeric_col_indices) > 1:
                    return ResultResolutionOutcome.not_answerable(
                        "Ambiguous metric: multiple numeric columns exist. Specify which metric to evaluate."
                    )
                elif len(numeric_col_indices) == 1:
                    numeric_col_idx = numeric_col_indices[0]
                else:
                    numeric_col_idx = None
            else:
                numeric_col_idx = target_num_col_idx

            target_cat_col_idx = None
            for i in cat_col_indices:
                if re.search(r"\b" + re.escape(cols[i]) + r"\b", norm_q, re.IGNORECASE):
                    target_cat_col_idx = i
                    break
            cat_col_idx = target_cat_col_idx if target_cat_col_idx is not None else (cat_col_indices[0] if cat_col_indices else None)

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

            target_col_idx = None
            target_col_name = None
            for i, raw_col_name in enumerate(result_metadata.columns):
                col_clean, col_spaced, tokens = self._extract_column_tokens_and_phrases(raw_col_name)
                # 1. Exact or whole-word/phrase match on column name or spaced name
                if (
                    re.search(r"\b" + re.escape(col_clean) + r"\b", norm_q)
                    or re.search(r"\b" + re.escape(col_spaced) + r"\b", norm_q)
                ):
                    target_col_idx = i
                    target_col_name = raw_col_name
                    break
                # 2. Token-level match (e.g. column 'employee_salary' matches query containing 'salary')
                for token in tokens:
                    if re.search(r"\b" + re.escape(token) + r"\b", norm_q):
                        target_col_idx = i
                        target_col_name = raw_col_name
                        break
                if target_col_idx is not None:
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

            # Target entity found in result, but requested attribute column is not present
            if target_row_idx is not None and target_col_idx is None:
                return ResultResolutionOutcome.not_answerable(
                    "Target entity found in result, but requested attribute column is not present."
                )

        # 5. Text Summary Lookup
        eff_summary = summary or (result_metadata.summary if result_metadata else None)
        if eff_summary:
            words = [w for w in re.split(r"[\s,;?.'\"]+", norm_q) if len(w) > 3]
            for w in words:
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
