"""Query-time retrieval of a compact, join-complete semantic subgraph."""
from __future__ import annotations

from collections import deque
from typing import Any

from src.application.ports.semantic_repository import SemanticRepository


class ContextRetrievalService:
    """Retrieves relevant semantic slice and builds compact, join-complete LLM subgraphs.

    Performs vector similarity search against the approved Semantic Layer, identifies seed tables,
    calculates shortest-path connecting relationships to ensure all joins are complete,
    and formats a structured semantic context prompt block for LLM code generation.
    """

    def __init__(self, semantic_repository: SemanticRepository, default_top_k: int = 8) -> None:
        """Initialize the context retrieval service.

        Args:
            semantic_repository: Semantic repository port for loading and querying semantic data.
            default_top_k: Default number of top documents to retrieve from vector search.
        """
        self._semantic_repository = semantic_repository
        self._default_top_k = default_top_k

    def retrieve(self, question: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Retrieve top semantic document matches for a user question.

        Args:
            question: Natural language question.
            top_k: Optional limit on the number of documents; if None, computes dynamic candidate limit.

        Returns:
            List of semantic document dictionaries matched by vector similarity.
        """
        limit = top_k if top_k is not None else self._candidate_limit(question)
        return self._semantic_repository.retrieve(question, limit)

    def build_llm_context(self, question: str, top_k: int | None = None) -> str:
        """Construct a join-complete, formatted semantic context string for LLM prompts.

        Args:
            question: Natural language question.
            top_k: Optional top_k limit for initial document retrieval.

        Returns:
            Formatted plain-text block detailing approved entities, columns, relationships,
            query scope guidance, and business rules.
        """
        results = self.retrieve(question, top_k)
        layer = self._semantic_repository.load()
        requested_tables = self._planned_tables(question, layer)
        # For a multi-entity question, table coverage is more important than
        # allowing a few high-scoring attribute documents to introduce
        # unrelated tables.  The vector search above is deliberately wider;
        # this is the compact, approved-schema projection passed to the LLM.
        seed_tables = requested_tables | self._seed_tables(results)
        relationships = self._connecting_relationships(
            seed_tables, self._valid_relationships(layer.get("relationships", []))
        )
        tables = seed_tables | {
            table
            for relationship in relationships
            for table in (relationship["from_table"], relationship["to_table"])
        }
        lines = [
            "SEMANTIC CONTEXT",
            "This is a join-complete subgraph from the approved Semantic Layer.",
            "Use only the supplied tables, columns, and relationships.",
            "",
        ]
        self._append_entities(lines, layer.get("entities", []), tables)
        self._append_columns(lines, layer, tables)
        self._append_relationships(lines, relationships)
        self._append_query_scope(lines, seed_tables, relationships)
        self._append_retrieved_rules(lines, results)
        return "\n".join(lines)

    def _candidate_limit(self, question: str) -> int:
        """Return a wider retrieval candidate set for multi-table questions.

        Semantic objects are indexed independently (one document per entity,
        dimension, measure, relationship, or rule).  A fixed eight-document
        search cannot reliably cover a question that explicitly mentions many
        tables.  This only widens the retrieval candidate set; the final LLM
        context remains restricted to the requested join-complete subgraph.
        """

        layer = self._semantic_repository.load()
        table_count = len(self._planned_tables(question, layer))
        if table_count < 3:
            return self._default_top_k
        return max(self._default_top_k, table_count * 4)

    @staticmethod
    def _tables_explicitly_requested(question: str, layer: dict[str, Any]) -> set[str]:
        """Match table/entity names as whole words, only from approved metadata."""

        normalized_question = " ".join(
            "".join(character if character.isalnum() else " " for character in question.casefold()).split()
        )
        words = set(normalized_question.split())
        tables: set[str] = set()
        for entity in layer.get("entities", []):
            if not isinstance(entity, dict):
                continue
            mapping = entity.get("mapping")
            name = entity.get("name")
            if not isinstance(mapping, str) or not mapping:
                continue
            labels = [mapping, name] if isinstance(name, str) else [mapping]
            for label in labels:
                normalized_label = " ".join(
                    "".join(character if character.isalnum() else " " for character in label.casefold()).split()
                )
                if not normalized_label:
                    continue
                label_words = normalized_label.split()
                singular_or_plural_match = (
                    len(label_words) == 1
                    and (label_words[0] in words or f"{label_words[0]}s" in words)
                )
                if normalized_label in normalized_question or singular_or_plural_match:
                    tables.add(mapping)
                    break
        return tables

    @classmethod
    def _planned_tables(cls, question: str, layer: dict[str, Any]) -> set[str]:
        """Build a deterministic, metadata-grounded table plan for a question.

        Entity mentions cover requests such as "customers with cards".  Metric
        and attribute names cover requests whose table is implicit, such as
        "average credit score".  Both sources are restricted to the approved
        semantic layer, so the planner cannot introduce a table the model was
        not authorized to use.
        """

        tables = cls._tables_explicitly_requested(question, layer)
        question_words = set(cls._normalized_words(question))
        for section in ("dimensions", "measures"):
            for item in layer.get(section, []):
                if not isinstance(item, dict):
                    continue
                mapping = item.get("mapping")
                name = item.get("name")
                if not isinstance(mapping, str) or "." not in mapping:
                    continue
                if isinstance(name, str) and cls._semantic_name_matches(name, question_words):
                    tables.add(mapping.split(".", 1)[0])
        return tables

    @staticmethod
    def _normalized_words(value: str) -> list[str]:
        return "".join(
            character if character.isalnum() else " " for character in value.casefold()
        ).split()

    @classmethod
    def _semantic_name_matches(cls, name: str, question_words: set[str]) -> bool:
        """Require a specific semantic phrase, not a generic one-word overlap."""

        name_words = set(cls._normalized_words(name))
        if len(name_words) < 2:
            return False
        # A phrase is relevant when all of its semantic words occur in the
        # question, or when all but one occur in a three-or-more-word label.
        # The latter covers "average transaction amount" -> "Transaction Amount".
        matched = len(name_words & question_words)
        return matched == len(name_words) or (
            len(name_words) >= 3 and matched >= len(name_words) - 1
        )

    @staticmethod
    def _seed_tables(results: list[dict[str, Any]]) -> set[str]:
        """Derive context only from retrieved semantic documents.

        The repository owns relevance ranking.  Do not add tables through a
        second keyword-matching pass here, otherwise the LLM context can grow
        beyond the vector-retrieved semantic slice.
        """

        tables: set[str] = set()
        for result in results:
            payload = result.get("payload", {})
            if not isinstance(payload, dict):
                continue
            mapping = payload.get("mapping")
            if isinstance(mapping, str) and mapping:
                tables.add(mapping.split(".", 1)[0])
            for key in ("from_table", "to_table"):
                if isinstance(payload.get(key), str):
                    tables.add(payload[key])
        return tables

    @staticmethod
    def _valid_relationships(relationships: Any) -> list[dict[str, Any]]:
        """Keep only relationships that can safely be rendered as SQL joins.

        The approved semantic revision is Backend-owned. An incomplete
        relationship must not crash request handling or be turned into a
        guessed join; it simply cannot participate in a join-complete prompt.
        """
        if not isinstance(relationships, list):
            return []
        required = ("from_table", "from_column", "to_table", "to_column")
        return [
            relationship
            for relationship in relationships
            if isinstance(relationship, dict)
            and all(
                isinstance(relationship.get(field), str) and relationship[field]
                for field in required
            )
        ]

    @staticmethod
    def _connecting_relationships(
        seed_tables: set[str], relationships: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return the union of shortest approved paths between seed tables."""
        if len(seed_tables) < 2:
            return []
        adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for relationship in relationships:
            source, target = relationship.get("from_table"), relationship.get("to_table")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            adjacency.setdefault(source, []).append((target, relationship))
            adjacency.setdefault(target, []).append((source, relationship))

        selected: dict[str, dict[str, Any]] = {}
        ordered_tables = sorted(seed_tables)
        for index, start in enumerate(ordered_tables):
            for end in ordered_tables[index + 1 :]:
                for relationship in ContextRetrievalService._shortest_path(start, end, adjacency):
                    selected[relationship["name"]] = relationship
        return [selected[name] for name in sorted(selected)]

    @staticmethod
    def _shortest_path(
        start: str, end: str, adjacency: dict[str, list[tuple[str, dict[str, Any]]]]
    ) -> list[dict[str, Any]]:
        queue: deque[tuple[str, list[dict[str, Any]]]] = deque([(start, [])])
        visited = {start}
        while queue:
            table, path = queue.popleft()
            if table == end:
                return path
            for next_table, relationship in adjacency.get(table, []):
                if next_table not in visited:
                    visited.add(next_table)
                    queue.append((next_table, [*path, relationship]))
        return []

    @staticmethod
    def _append_entities(lines: list[str], entities: list[dict[str, Any]], tables: set[str]) -> None:
        for entity in entities:
            if entity.get("mapping") in tables:
                lines.append(f"ENTITY: {entity['name']} -> {entity['mapping']}")
        if tables:
            lines.append("")

    @staticmethod
    def _append_columns(lines: list[str], layer: dict[str, Any], tables: set[str]) -> None:
        objects = [*layer.get("dimensions", []), *layer.get("measures", [])]
        for table in sorted(tables):
            mappings = []
            for item in objects:
                mapping = item.get("mapping") if isinstance(item, dict) else None
                if isinstance(mapping, str) and mapping.startswith(f"{table}."):
                    mappings.append(f"{mapping.split('.', 1)[1]} ({item['name']})")
            if mappings:
                lines.extend((f"TABLE: {table}", "COLUMNS: " + ", ".join(sorted(set(mappings))), ""))

    @staticmethod
    def _append_relationships(lines: list[str], relationships: list[dict[str, Any]]) -> None:
        if not relationships:
            return
        lines.append("APPROVED RELATIONSHIPS:")
        for relationship in relationships:
            lines.append(
                f"- {relationship['from_table']}.{relationship['from_column']} "
                f"-> {relationship['to_table']}.{relationship['to_column']}"
            )
        lines.append("")

    @staticmethod
    def _append_query_scope(
        lines: list[str], seed_tables: set[str], relationships: list[dict[str, Any]]
    ) -> None:
        """Add compact, deterministic guidance for complex aggregation shape."""

        if not seed_tables:
            return
        lines.extend((
            "QUERY SCOPE:",
            "- Required tables: " + ", ".join(sorted(seed_tables)),
        ))
        degree: dict[str, int] = {}
        for relationship in relationships:
            for table in (relationship["from_table"], relationship["to_table"]):
                degree[table] = degree.get(table, 0) + 1
        if any(count >= 3 for count in degree.values()):
            lines.append(
                "- SAFE AGGREGATION: For independent one-to-many paths, aggregate each "
                "path to the requested grain in a separate CTE or subquery before joining "
                "the aggregates. Do not join raw child rows together before SUM, COUNT, or AVG."
            )
        lines.append("")

    @staticmethod
    def _append_retrieved_rules(lines: list[str], results: list[dict[str, Any]]) -> None:
        rules = [
            result["payload"] for result in results
            if result.get("type") == "business_rule" and isinstance(result.get("payload"), dict)
        ]
        if rules:
            lines.append("RETRIEVED BUSINESS RULES:")
            lines.extend(f"- {rule['description']}" for rule in rules if rule.get("description"))
