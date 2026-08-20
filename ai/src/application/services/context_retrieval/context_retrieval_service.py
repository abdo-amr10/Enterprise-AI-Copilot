"""Query-time retrieval of a compact, join-complete semantic subgraph."""
from __future__ import annotations

from collections import deque
import re
from typing import Any

from src.application.ports.semantic_repository import SemanticRepository


class ContextRetrievalService:
    """Retrieve seed objects, then complete the joins they require."""

    def __init__(self, semantic_repository: SemanticRepository, default_top_k: int = 8) -> None:
        self._semantic_repository = semantic_repository
        self._default_top_k = default_top_k

    def retrieve(self, question: str, top_k: int | None = None) -> list[dict[str, Any]]:
        limit = top_k if top_k is not None else self._default_top_k
        return self._semantic_repository.retrieve(question, limit)

    def build_llm_context(self, question: str, top_k: int | None = None) -> str:
        results = self.retrieve(question, top_k)
        layer = self._semantic_repository.load()
        seed_tables = self._seed_tables(question, results, layer)
        relationships = self._connecting_relationships(
            seed_tables, layer.get("relationships", [])
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
        self._append_retrieved_rules(lines, results)
        return "\n".join(lines)

    @staticmethod
    def _seed_tables(question: str, results: list[dict[str, Any]], layer: dict[str, Any]) -> set[str]:
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

        question_words = set(re.findall(r"[a-z]+", question.casefold().replace("'s", "")))
        for entity in layer.get("entities", []):
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name", "")).casefold()
            mapping = entity.get("mapping")
            if isinstance(mapping, str) and (name in question_words or f"{name}s" in question_words):
                tables.add(mapping)
        return tables

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
    def _append_retrieved_rules(lines: list[str], results: list[dict[str, Any]]) -> None:
        rules = [
            result["payload"] for result in results
            if result.get("type") == "business_rule" and isinstance(result.get("payload"), dict)
        ]
        if rules:
            lines.append("RETRIEVED BUSINESS RULES:")
            lines.extend(f"- {rule['description']}" for rule in rules if rule.get("description"))
