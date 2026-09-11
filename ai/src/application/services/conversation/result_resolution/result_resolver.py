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
        "eleventh": 11,
        "11th": 11,
        "twelfth": 12,
        "12th": 12,
        "thirteenth": 13,
        "13th": 13,
        "fourteenth": 14,
        "14th": 14,
        "fifteenth": 15,
        "15th": 15,
        "sixteenth": 16,
        "16th": 16,
        "seventeenth": 17,
        "17th": 17,
        "eighteenth": 18,
        "18th": 18,
        "nineteenth": 19,
        "19th": 19,
        "twentieth": 20,
        "20th": 20,
        "الأول": 1,
        "الاول": 1,
        "الثاني": 2,
        "التاني": 2,
        "الثالث": 3,
        "التالت": 3,
        "الرابع": 4,
        "الخامس": 5,
        "السادس": 6,
        "السابع": 7,
        "الثامن": 8,
        "التاسع": 9,
        "العاشر": 10,
    }

    _ORDINAL_PATTERN = re.compile(
        r"\b(?:who|what|which|how\s+about|what\s+about|and)(?:\s+one)?(?:\s+(?:is|was|about))?\s+(?:#|number|no\.?|num\.?)?\s*(\d+)\b|"
        r"\b(?:who|what|which)(?:\s+is|\s+was)?\s+(?:the\s+)?([a-z0-9\u0600-\u06FF]+)(?:\s+(?:one|row|item|record|result))?\b|"
        r"\b(?:the\s+)?([a-z0-9\u0600-\u06FF]+)\s+(?:one|row|item|record|result)\b|"
        r"^(?:#|number|no\.?)\s*(\d+)\??$|"
        r"\b(?:مين|إيه|ما|وريني|اعرض)?\s*(?:هو|هي)?\s*(?:رقم|الرقم|المرتبة|المركز)\s*(\d+)\b",
        re.IGNORECASE | re.UNICODE,
    )

    _COUNT_PATTERN = re.compile(
        r"\b(?:how\s+many(?:\s+[a-zA-Z_]+)?|count|total\s+rows)\b",
        re.IGNORECASE,
    )

    _EXTREME_PATTERN = re.compile(
        r"\b(?:which|who|what)(?:\s+[a-zA-Z_]+)?\s+(?:is|has|was|had)?\s*(?:the\s+)?(highest|maximum|max|top|lowest|minimum|min)\b",
        re.IGNORECASE,
    )

    _SUMMARY_REPLAY_PATTERN = re.compile(
        r"\b(?:(?:repeat|show|give|display|get|what\s+is|what\s+was|what\s+(?:is\s+)?the|tell\s+me|read)\s+(?:me\s+)?(?:the\s+)?(?:executive\s+)?summ?a?r?y|"
        r"(?:executive\s+)?summ?a?r?y(?:\s+(?:of|about|for)?\s+(?:the\s+)?(?:result|results|query|data))?|"
        r"summarize(?:\s+(?:the\s+)?(?:result|results|data))?|"
        r"what\s+(?:is\s+)?(?:the\s+)?summ?a?r?y\s+(?:about|of|for)?\s*(?:the\s+)?(?:result|results)?|"
        r"(?:عيد|أعد|اعرض|وريني|هات|طلع|إيه\s+هو|ما\s+هو)?\s*(?:ال)?ملخص(?:\s+(?:التنفيذي|النتيجة))?|"
        r"لخص(?:\s+(?:لي\s+)?النتيجة)?)\b",
        re.IGNORECASE | re.UNICODE,
    )

    _LIST_ROWS_PATTERN = re.compile(
        r"\b(?:who\s+(?:are|were)\s+(?:they|these|those|them)|what\s+(?:are|were)\s+(?:they|these|those|the\s+results)|"
        r"list\s+(?:them|the\s+results|the\s+rows)|show\s+(?:them|the\s+results|the\s+rows|me\s+the\s+results)|"
        r"مين\s+(?:هم|هما|دول)|إيه\s+(?:هم|هما|دول)|اعرضهم|وريني\s+إياهم|اعرض\s+النتائج|وريني\s+النتائج|طلع\s+لي\s+النتائج|"
        r"(?:ال)?(?:خمسة|عشرة|\d+)\s+دول|دول\s+مين)\b",
        re.IGNORECASE | re.UNICODE,
    )

    _ARABIC_TO_LATIN_COMMON = {
        "سارة": "sara",
        "ساره": "sara",
        "احمد": "ahmed",
        "أحمد": "ahmed",
        "محمد": "mohamed",
        "علي": "ali",
        "خالد": "khaled",
        "تامر": "tamer",
        "محمود": "mahmoud",
        "عمرو": "amr",
        "منى": "mona",
        "مني": "mona",
        "طارق": "tarek",
        "حسن": "hassan",
        "حسين": "hussein",
        "ابراهيم": "ibrahim",
        "إبراهيم": "ibrahim",
        "مريم": "mariam",
        "فاطمة": "fatima",
        "نور": "nour",
    }

    _DATABASE_QUERY_INSTRUCTION_PATTERN = re.compile(
        r"\b(?:show|list|get|find|select|fetch|query|calculate|sum|count|average|extract|pull|"
        r"for\s+(?:those|these|the\s+same|each|them)|"
        r"among\s+(?:those|these|them)|"
        r"where|whose|using|group\s+by|order\s+by|greater\s+than|less\s+than|[><=])\b",
        re.IGNORECASE,
    )

    _SCHEMA_AND_COMMON_TERMS = {
        "branch", "branches", "account", "accounts", "transaction", "transactions",
        "customer", "customers", "loan", "loans", "card", "cards", "merchant", "merchants",
        "id", "name", "date", "status", "type", "amount", "balance", "total", "city",
        "country", "rate", "score", "credit", "first", "last", "email", "created",
        "open", "value", "table", "data", "query", "record", "row", "usd", "code",
        "all", "top", "only", "same", "new", "each", "these", "those",
    }

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

        # 0. Summary Replay (e.g. "عيد الملخص", "what was the summary", "executive summary")
        eff_summary = summary or (result_metadata.summary if result_metadata else None)
        if self._SUMMARY_REPLAY_PATTERN.search(norm_q):
            if eff_summary:
                return ResultResolutionOutcome.answerable(eff_summary, confidence=1.0)
            return ResultResolutionOutcome.not_answerable("No summary available for previous result.")

        # 0b. List rows / Show results (e.g. "who are they", "list them", "الخمسة دول")
        if self._LIST_ROWS_PATTERN.search(norm_q) and result_metadata and result_metadata.sample_rows:
            formatted_rows = []
            cols = result_metadata.columns
            for r in result_metadata.sample_rows[:15]:
                if cols and len(cols) == len(r):
                    row_str = ", ".join(f"{c}: {v}" for c, v in zip(cols, r) if v is not None)
                else:
                    row_str = ", ".join(str(v) for v in r if v is not None)
                formatted_rows.append(row_str)
            return ResultResolutionOutcome.answerable(
                "\n".join(formatted_rows),
                confidence=0.95,
            )

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
                elif len(groups) > 4 and groups[4]:
                    rank = int(groups[4])

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

        # If the question is a database query/instruction, NEVER answer from result metadata/summary
        if self._DATABASE_QUERY_INSTRUCTION_PATTERN.search(norm_q):
            return ResultResolutionOutcome.not_answerable(
                "Database query instruction must proceed to context resolution and Text-to-SQL pipeline."
            )

        # 4. Cell / Attribute lookup (e.g. "What department is Sara in?", "What was Sara's salary?", "Tell me about Ahmed")
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

            # Identify target rows by matching any string/numeric cell value against query words
            matched_rows = []
            for row_idx, row in enumerate(rows):
                for cell_idx, cell in enumerate(row):
                    if cell is not None and isinstance(cell, (str, int, float)):
                        cell_clean = str(cell).strip().lower()
                        # Strictly skip common schema/domain terms (like "branch", "account", "status")
                        if cell_clean in self._SCHEMA_AND_COMMON_TERMS or len(cell_clean) < 3:
                            continue

                        is_match = bool(re.search(r"\b" + re.escape(cell_clean) + r"\b", norm_q))
                        if not is_match:
                            # Cross-script transliteration check
                            ar_variant = self._ARABIC_TO_LATIN_COMMON.get(cell_clean)
                            if ar_variant and re.search(r"\b" + re.escape(ar_variant) + r"\b", norm_q):
                                is_match = True
                            elif not ar_variant:
                                for ar_w, en_w in self._ARABIC_TO_LATIN_COMMON.items():
                                    if en_w == cell_clean and ar_w in norm_q:
                                        is_match = True
                                        break
                        if is_match:
                            matched_rows.append((row_idx, row))
                            break

            if matched_rows:
                # If a specific column was matched in the query
                if target_col_idx is not None:
                    if len(matched_rows) == 1:
                        target_row_idx = matched_rows[0][0]
                        cell_value = rows[target_row_idx][target_col_idx]
                        return ResultResolutionOutcome.answerable(
                            str(cell_value),
                            column=target_col_name,
                            row_index=target_row_idx,
                        )
                    else:
                        lines = []
                        for r_idx, r in matched_rows[:15]:
                            ent_label = str(r[0]) if len(r) > 0 else f"Row {r_idx + 1}"
                            lines.append(f"{ent_label}: {r[target_col_idx]}")
                        return ResultResolutionOutcome.answerable(
                            "\n".join(lines),
                            column=target_col_name,
                        )

                # If no specific column was matched, check if an unrepresented attribute was explicitly requested
                attr_match = re.search(r"\b(?:what|which)\s+([a-zA-Z_]+)\s+(?:is|was|are|were|does|has|had)\b", norm_q)
                if not attr_match:
                    attr_match = re.search(r"\b(?:what\s+is|what\s+was|tell\s+me)\s+(?:the\s+)?([a-zA-Z_]+)\s+of\b", norm_q)
                if not attr_match:
                    attr_match = re.search(r"[\w]+'s\s+([a-zA-Z_]+)\b", norm_q)

                if attr_match:
                    potential_attr = attr_match.group(1).lower()
                    generic_attr_words = {
                        "data", "info", "details", "record", "row", "profile",
                        "status", "result", "about", "is", "was", "are", "were",
                        "one", "person", "item", "the",
                    }
                    if potential_attr not in generic_attr_words:
                        return ResultResolutionOutcome.not_answerable(
                            f"Target entity found in result, but requested attribute '{potential_attr}' is not present."
                        )

                # If the user is asking about the matched entity or its row details (e.g. "بيانات سارة", "what about John"):
                # Only answer if query explicitly exhibits entity-inspection intent
                is_entity_inspection = bool(re.search(
                    r"\b(?:tell\s+me\s+about|what\s+about|details\s+of|profile\s+of|بيانات|معلومات|عن)\b",
                    norm_q,
                    re.IGNORECASE,
                ))
                if is_entity_inspection:
                    formatted = []
                    for r_idx, r in matched_rows[:15]:
                        if result_metadata.columns and len(result_metadata.columns) == len(r):
                            row_str = ", ".join(f"{c}: {v}" for c, v in zip(result_metadata.columns, r) if v is not None)
                        else:
                            row_str = ", ".join(str(v) for v in r if v is not None)
                        formatted.append(row_str)

                    return ResultResolutionOutcome.answerable(
                        "\n".join(formatted),
                        row_index=matched_rows[0][0] if len(matched_rows) == 1 else None,
                        confidence=0.95,
                    )

        return ResultResolutionOutcome.not_answerable("Question cannot be answered directly from the previous result.")
