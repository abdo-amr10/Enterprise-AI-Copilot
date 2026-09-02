"""Optional sample data analysis for empirical relationship evidence."""

from __future__ import annotations

from typing import Any


class SampleDataAnalyzer:
    """Extracts empirical evidence from optional database sample data."""

    def __init__(self, sample_data: Any | None = None) -> None:
        self._table_data = self._extract_table_data(sample_data)

    def is_available(self) -> bool:
        """Return True if sample data is present for at least one table."""
        return bool(self._table_data)

    def analyze_pair(
        self,
        source_table: str,
        source_column: str,
        target_table: str,
        target_column: str,
    ) -> dict[str, float | None]:
        """Compute value overlap, directional containment, and uniqueness metrics.

        Returns:
            Dictionary containing:
            - 'overlap': Jaccard similarity (0.0 to 1.0) or None
            - 'containment': Fraction of source values found in target (0.0 to 1.0) or None
            - 'uniqueness': Target column distinctness ratio (0.0 to 1.0) or None
        """
        if not self._table_data:
            return {"overlap": None, "containment": None, "uniqueness": None}

        source_vals = self._get_column_values(source_table, source_column)
        target_vals = self._get_column_values(target_table, target_column)

        if not source_vals or not target_vals:
            return {"overlap": None, "containment": None, "uniqueness": None}

        source_set = set(source_vals)
        target_set = set(target_vals)

        if not source_set or not target_set:
            return {"overlap": 0.0, "containment": 0.0, "uniqueness": 0.0}

        intersection = source_set & target_set
        union = source_set | target_set

        overlap = len(intersection) / len(union) if union else 0.0
        containment = len(intersection) / len(source_set) if source_set else 0.0
        uniqueness = len(target_set) / len(target_vals) if target_vals else 0.0

        return {
            "overlap": round(overlap, 4),
            "containment": round(containment, 4),
            "uniqueness": round(uniqueness, 4),
        }

    def _get_column_values(self, table_name: str, column_name: str) -> list[str]:
        """Extract non-null, stripped string values for a table column."""
        rows = self._table_data.get(table_name.casefold(), [])
        values: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # Try exact and casefold column lookup
            val = row.get(column_name)
            if val is None:
                for k, v in row.items():
                    if k.casefold() == column_name.casefold():
                        val = v
                        break
            if val is not None:
                s = str(val).strip()
                if s and s.casefold() not in ("null", "none", ""):
                    values.append(s)
        return values

    @staticmethod
    def _extract_table_data(sample_data: Any) -> dict[str, list[dict[str, Any]]]:
        """Normalize various sample data structures into a per-table dictionary of row dictionaries."""
        if not sample_data:
            return {}

        result: dict[str, list[dict[str, Any]]] = {}

        # Case 1: Dict of tables -> rows (e.g. {"customers": [{...}, {...}], "orders": [...]})
        if isinstance(sample_data, dict):
            for table_name, rows in sample_data.items():
                if isinstance(rows, list):
                    result[table_name.casefold()] = [r for r in rows if isinstance(r, dict)]
                elif isinstance(rows, dict) and "rows" in rows and isinstance(rows["rows"], list):
                    result[table_name.casefold()] = [r for r in rows["rows"] if isinstance(r, dict)]
            return result

        # Case 2: List of flat records or mixed records
        if isinstance(sample_data, list):
            # If records have a "_table" or "table" property
            for item in sample_data:
                if isinstance(item, dict):
                    table_name = item.get("_table") or item.get("table") or item.get("tableName")
                    if table_name and isinstance(table_name, str):
                        clean_row = {k: v for k, v in item.items() if k not in ("_table", "table", "tableName")}
                        result.setdefault(table_name.casefold(), []).append(clean_row)

        return result
