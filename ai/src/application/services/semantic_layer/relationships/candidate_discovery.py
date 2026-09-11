"""Relationship Candidate Discovery Engine."""

from __future__ import annotations

from typing import Any
from src.application.services.semantic_layer.relationships.classifier import RelationshipClassifier
from src.application.services.semantic_layer.relationships.models import (
    EvidenceBreakdown,
    NormalizedColumn,
    NormalizedSchema,
    NormalizedTable,
    ScoringConfig,
)
from src.application.services.semantic_layer.relationships.registry import RelationshipRegistry
from src.application.services.semantic_layer.relationships.sample_data_analyzer import SampleDataAnalyzer
from src.application.services.semantic_layer.relationships.scorer import RelationshipScorer


class CandidateDiscoveryEngine:
    """Discovers unprovided relationship candidates based on schema, type, and optional sample evidence."""

    def __init__(
        self,
        scorer: RelationshipScorer | None = None,
        classifier: RelationshipClassifier | None = None,
        config: ScoringConfig | None = None,
    ) -> None:
        self.config = config or ScoringConfig()
        self.scorer = scorer or RelationshipScorer(self.config)
        self.classifier = classifier or RelationshipClassifier(self.config)

    def discover_candidates(
        self,
        schema: NormalizedSchema,
        registry: RelationshipRegistry,
        sample_analyzer: SampleDataAnalyzer | None = None,
        glossary_terms: list[str] | None = None,
    ) -> None:
        """Scan schema for relationship candidates and register them."""
        tables = list(schema.tables.values())
        discovered_by_source: dict[tuple[str, str], list[tuple[NormalizedTable, NormalizedColumn, float, EvidenceBreakdown]]] = {}

        for i, source_table in enumerate(tables):
            for target_table in tables:
                if source_table.original_name == target_table.original_name:
                    continue

                for source_col in source_table.columns.values():
                    for target_col in target_table.columns.values():
                        # Phase 3 & 4 Rule: Never rediscover already registered or provided relationships
                        if registry.is_registered(
                            source_table.original_name,
                            source_col.original_name,
                            target_table.original_name,
                            target_col.original_name,
                        ):
                            continue

                        # Check candidate trigger signals
                        if not self._is_candidate_trigger(source_table, source_col, target_table, target_col):
                            continue

                        # Optional empirical sample data
                        sample_metrics = (
                            sample_analyzer.analyze_pair(
                                source_table.original_name,
                                source_col.original_name,
                                target_table.original_name,
                                target_col.original_name,
                            )
                            if sample_analyzer and sample_analyzer.is_available()
                            else None
                        )

                        # Semantic hint from glossary
                        semantic_score = self._compute_semantic_hint(
                            source_col, target_col, glossary_terms
                        )

                        confidence, evidence = self.scorer.score_candidate(
                            source_table=source_table,
                            source_column=source_col,
                            target_table=target_table,
                            target_column=target_col,
                            sample_metrics=sample_metrics,
                            semantic_hint_score=semantic_score,
                        )

                        source_key = (source_table.original_name, source_col.original_name)
                        discovered_by_source.setdefault(source_key, []).append(
                            (target_table, target_col, confidence, evidence)
                        )

        # Process ambiguity and register classified candidates
        for (src_tbl, src_col), candidates in discovered_by_source.items():
            # Sort candidates by confidence descending
            sorted_candidates = sorted(candidates, key=lambda x: x[2], reverse=True)

            if not sorted_candidates:
                continue

            top_tgt_tbl, top_tgt_col, top_conf, top_ev = sorted_candidates[0]

            # Check if ambiguous (e.g. multiple candidates with score close to top score)
            is_ambiguous = False
            if len(sorted_candidates) > 1 and top_conf >= self.config.probabilistic_threshold:
                second_conf = sorted_candidates[1][2]
                if (top_conf - second_conf) < self.config.uncertain_ambiguity_margin:
                    is_ambiguous = True

            for tgt_tbl, tgt_col, conf, ev in sorted_candidates:
                candidate_id = f"rel-inferred-{src_tbl}-{src_col}-{tgt_tbl.original_name}-{tgt_col.original_name}"
                name = f"{src_tbl}_{tgt_tbl.original_name}_{src_col}"

                is_cand_ambiguous = is_ambiguous and (top_conf - conf <= self.config.uncertain_ambiguity_margin)

                classified = self.classifier.classify_inferred_candidate(
                    candidate_id=candidate_id,
                    name=name,
                    source_table=src_tbl,
                    source_column=src_col,
                    target_table=tgt_tbl.original_name,
                    target_column=tgt_col.original_name,
                    confidence=conf,
                    evidence=ev,
                    is_ambiguous=is_cand_ambiguous,
                    schema_version=schema.version,
                )

                registry.register_candidate(classified)

    @staticmethod
    def _is_candidate_trigger(
        source_table: NormalizedTable,
        source_col: NormalizedColumn,
        target_table: NormalizedTable,
        target_col: NormalizedColumn,
    ) -> bool:
        """Filter out non-candidate column pairs before expensive scoring."""
        src_col_norm = source_col.normalized_name
        src_tbl_stem = source_table.normalized_name.rstrip("s")
        tgt_tbl_stem = target_table.normalized_name.rstrip("s")

        # 1. If source column is a primary key, it can only relate to a target column with the same name (1:1 extension)
        if source_col.is_primary_key and src_col_norm != target_col.normalized_name:
            return False

        # 2. Source column must have key naming pattern or share name with target table/column
        has_src_key_pattern = (
            src_col_norm.endswith("_id")
            or src_col_norm.endswith("_key")
            or src_col_norm.endswith("_fk")
            or src_col_norm.endswith("_code")
            or src_col_norm.startswith("id_")
            or src_col_norm == target_col.normalized_name
            or src_col_norm.startswith(tgt_tbl_stem)
        )
        if not has_src_key_pattern:
            return False

        # 3. Target column must be a key, PK, unique, or share column name
        has_tgt_key_pattern = (
            target_col.normalized_name == "id"
            or target_col.normalized_name.endswith("_id")
            or target_col.normalized_name.endswith("_key")
            or target_col.is_primary_key
            or target_col.unique
            or src_col_norm == target_col.normalized_name
        )
        if not has_tgt_key_pattern:
            return False

        # 4. Strict rule: generic non-key column names are never FK triggers
        generic_non_fk_names = {
            "status", "name", "description", "created_at", "updated_at",
            "is_active", "type", "date", "amount", "total", "value", "data"
        }
        if src_col_norm in generic_non_fk_names and not source_col.is_primary_key:
            return False

        return True



    @staticmethod
    def _compute_semantic_hint(
        source_col: NormalizedColumn,
        target_col: NormalizedColumn,
        glossary_terms: list[str] | None,
    ) -> float:
        """Compute lightweight glossary/semantic overlap score."""
        if not glossary_terms:
            return 0.0
        src_n = source_col.normalized_name
        tgt_n = target_col.normalized_name
        for term in glossary_terms:
            t = term.casefold()
            if src_n in t and tgt_n in t:
                return 0.8
        return 0.0
