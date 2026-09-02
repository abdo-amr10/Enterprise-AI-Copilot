"""Evidence-based relationship scoring model."""

from __future__ import annotations

import difflib
import re
from typing import Any
from src.application.services.semantic_layer.relationships.models import (
    EvidenceBreakdown,
    NormalizedColumn,
    NormalizedTable,
    ScoringConfig,
)
from src.application.services.semantic_layer.relationships.normalizer import SchemaNormalizer


class RelationshipScorer:
    """Computes multidimensional evidence scores for relationship candidates."""

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig()

    def score_candidate(
        self,
        source_table: NormalizedTable,
        source_column: NormalizedColumn,
        target_table: NormalizedTable,
        target_column: NormalizedColumn,
        sample_metrics: dict[str, float | None] | None = None,
        semantic_hint_score: float = 0.0,
    ) -> tuple[float, EvidenceBreakdown]:
        """Compute multidimensional evidence and final composite confidence score.

        Returns:
            Tuple of (confidence_score, EvidenceBreakdown)
        """
        explanations: list[str] = []

        # 1. Type compatibility
        type_compat = self._compute_type_compatibility(
            source_column.data_type, target_column.data_type
        )
        if type_compat == 0.0:
            explanations.append(
                f"Data types incompatible ('{source_column.data_type}' vs '{target_column.data_type}')."
            )
        elif type_compat < 1.0:
            explanations.append(
                f"Data types partially compatible ('{source_column.data_type}' vs '{target_column.data_type}')."
            )

        # 2. PK / Key Signal
        pk_signal = self._compute_pk_signal(source_column, target_column)
        if target_column.is_primary_key:
            explanations.append(f"Target column '{target_table.original_name}.{target_column.original_name}' is a primary key.")
        elif target_column.unique:
            explanations.append(f"Target column '{target_table.original_name}.{target_column.original_name}' is unique.")

        # 3. Foreign Key Naming Pattern
        fk_pattern = self._compute_fk_pattern(source_table, source_column, target_table, target_column)
        if fk_pattern >= 0.8:
            explanations.append(
                f"Source column '{source_column.original_name}' follows strong foreign-key naming for target table '{target_table.original_name}'."
            )

        # 4. Name similarity
        name_sim = self._compute_name_similarity(source_column.original_name, target_column.original_name)
        norm_sim = self._compute_name_similarity(source_column.normalized_name, target_column.normalized_name)

        # 5. Sample metrics
        sample_overlap = sample_metrics.get("overlap") if sample_metrics else None
        sample_containment = sample_metrics.get("containment") if sample_metrics else None
        sample_uniqueness = sample_metrics.get("uniqueness") if sample_metrics else None

        if sample_overlap is not None and sample_overlap > 0.5:
            explanations.append(f"Sample data confirms value overlap ({sample_overlap * 100:.1f}%).")
        if sample_containment is not None and sample_containment > 0.8:
            explanations.append(f"Sample data confirms high value containment ({sample_containment * 100:.1f}%).")

        evidence = EvidenceBreakdown(
            name_similarity=round(name_sim, 4),
            normalized_similarity=round(norm_sim, 4),
            type_compatibility=round(type_compat, 4),
            pk_signal=round(pk_signal, 4),
            fk_naming_pattern=round(fk_pattern, 4),
            sample_overlap=sample_overlap,
            sample_containment=sample_containment,
            sample_uniqueness=sample_uniqueness,
            semantic_similarity=round(semantic_hint_score, 4),
            explanations=explanations,
        )

        # STRICT GUARDS:
        # 1. Incompatible types immediately drop score to 0.0
        if type_compat <= 0.0:
            return 0.0, evidence

        # 2. If no FK naming pattern and no meaningful name similarity, PK presence alone cannot create a relationship
        if fk_pattern == 0.0 and max(name_sim, norm_sim) < 0.6:
            explanations.append("Rejected: No foreign-key naming pattern or column name connection.")
            return 0.0, evidence

        # 3. If neither column has PK signal and neither has FK pattern, similarity alone cannot establish a relationship
        if pk_signal == 0.0 and fk_pattern < 0.5:
            explanations.append("Rejected: Name similarity without PK or FK structural signals.")
            return 0.0, evidence


        # Calculate weighted confidence
        has_sample = (sample_overlap is not None and sample_containment is not None)
        if has_sample:
            confidence = (
                self.config.weight_with_sample_name_similarity * name_sim
                + self.config.weight_with_sample_normalized_similarity * norm_sim
                + self.config.weight_with_sample_type_compatibility * type_compat
                + self.config.weight_with_sample_pk_signal * pk_signal
                + self.config.weight_with_sample_fk_naming_pattern * fk_pattern
                + self.config.weight_with_sample_overlap * (sample_overlap or 0.0)
                + self.config.weight_with_sample_containment * (sample_containment or 0.0)
                + self.config.weight_with_sample_semantic_similarity * semantic_hint_score
            )
        else:
            confidence = (
                self.config.weight_name_similarity * name_sim
                + self.config.weight_normalized_similarity * norm_sim
                + self.config.weight_type_compatibility * type_compat
                + self.config.weight_pk_signal * pk_signal
                + self.config.weight_fk_naming_pattern * fk_pattern
                + self.config.weight_semantic_similarity * semantic_hint_score
            )

        # High-confidence bonus when all structural criteria are strongly aligned:
        # FK name exactly matches target table + PK (e.g. orders.customer_id -> customers.id or customers.customer_id)
        if fk_pattern >= 0.9 and pk_signal >= 0.9 and type_compat >= 1.0:
            confidence = max(confidence, 0.85)

        return min(max(round(confidence, 4), 0.0), 1.0), evidence

    @staticmethod
    def _compute_type_compatibility(type_a: str | None, type_b: str | None) -> float:
        """Determine compatibility score between two column types."""
        if not type_a or not type_b:
            return 0.8  # Type unverified, treat with slight caution

        ta = type_a.casefold().strip()
        tb = type_b.casefold().strip()

        # Exact match (e.g. "int" == "int", "varchar(50)" == "varchar(50)")
        if ta == tb:
            return 1.0

        # Strip length/precision: varchar(50) -> varchar
        base_a = re.sub(r"\(.*?\)", "", ta).strip()
        base_b = re.sub(r"\(.*?\)", "", tb).strip()

        if base_a == base_b:
            return 1.0

        # Integer family
        int_types = {"int", "integer", "bigint", "smallint", "tinyint", "number"}
        if base_a in int_types and base_b in int_types:
            return 0.95

        # String / text family
        str_types = {"varchar", "nvarchar", "text", "ntext", "char", "nchar", "string"}
        if base_a in str_types and base_b in str_types:
            return 0.95

        # UUID / GUID family
        uuid_types = {"uniqueidentifier", "uuid", "guid"}
        if base_a in uuid_types and base_b in uuid_types:
            return 1.0
        if (base_a in uuid_types and base_b in str_types) or (base_b in uuid_types and base_a in str_types):
            return 0.8

        # Date / timestamp family
        date_types = {"date", "datetime", "datetime2", "timestamp", "smalldatetime"}
        if base_a in date_types and base_b in date_types:
            return 0.9

        # Incompatible families (e.g. int vs varchar, datetime vs int)
        return 0.0

    @staticmethod
    def _compute_pk_signal(source_col: NormalizedColumn, target_col: NormalizedColumn) -> float:
        """Score the primary key / uniqueness orientation of the target column."""
        if target_col.is_primary_key:
            return 1.0
        if target_col.unique:
            return 0.9
        if target_col.normalized_name == "id" or target_col.normalized_name.endswith("_id") or target_col.normalized_name.endswith("_key"):
            return 0.75  # Likely target primary identifier
        if source_col.is_primary_key:
            return 0.7  # Possible reverse-direction candidate
        return 0.0


    @staticmethod
    def _compute_fk_pattern(
        source_table: NormalizedTable,
        source_col: NormalizedColumn,
        target_table: NormalizedTable,
        target_col: NormalizedColumn,
    ) -> float:
        """Detect foreign-key naming patterns linking source column to target table."""
        src_col_norm = source_col.normalized_name
        tgt_tbl_norm = target_table.normalized_name
        # Remove trailing 's' / 'es' from target table for singular comparison (e.g. customers -> customer)
        singular_tgt_tbl = re.sub(r"e?s$", "", tgt_tbl_norm)

        # Pattern 1: Exact target table + "_id" or "_key" (e.g. customer_id -> customers)
        if src_col_norm in (f"{tgt_tbl_norm}_id", f"{singular_tgt_tbl}_id", f"{tgt_tbl_norm}_key", f"{singular_tgt_tbl}_key"):
            return 1.0

        # Pattern 2: Target column is 'id' and source column is '<target>_id'
        if target_col.normalized_name == "id" and (src_col_norm.startswith(singular_tgt_tbl) or src_col_norm.endswith("_id")):
            return 0.9

        # Pattern 3: Both columns share the exact same key name ending in _id (e.g. orders.customer_id and customers.customer_id)
        if src_col_norm == target_col.normalized_name and (src_col_norm.endswith("_id") or src_col_norm.endswith("_key") or src_col_norm.endswith("_code")):
            return 0.95

        # Pattern 4: General ID suffix without direct table name match (e.g. cust_id -> customers)
        if src_col_norm.endswith("_id") or src_col_norm.endswith("_fk") or src_col_norm.startswith("id_"):
            # Check for substring / abbreviation overlap (e.g. cust in customer)
            prefix = src_col_norm.split("_")[0]
            if len(prefix) >= 3 and prefix in singular_tgt_tbl:
                return 0.85
            return 0.5

        return 0.0

    @staticmethod
    def _compute_name_similarity(name_a: str, name_b: str) -> float:
        """Compute string similarity ratio between 0.0 and 1.0."""
        if not name_a or not name_b:
            return 0.0
        if name_a.casefold() == name_b.casefold():
            return 1.0
        return difflib.SequenceMatcher(None, name_a.casefold(), name_b.casefold()).ratio()
