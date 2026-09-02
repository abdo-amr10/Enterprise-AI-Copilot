"""Graph modeling and disconnected entity/component detection."""

from __future__ import annotations

from collections import deque
from typing import Any
from src.application.services.semantic_layer.relationships.models import (
    DisconnectedAnalysisResult,
    DisconnectedComponent,
    NormalizedSchema,
    ProcessedRelationship,
)


class RelationshipGraph:
    """Represents tables as nodes and validated relationships as edges."""

    def __init__(self, schema: NormalizedSchema, relationships: list[ProcessedRelationship]) -> None:
        self.schema = schema
        self.relationships = relationships
        self._adjacency: dict[str, list[tuple[str, ProcessedRelationship]]] = {
            table_name: [] for table_name in schema.tables
        }
        self._build_graph()

    def _build_graph(self) -> None:
        """Construct graph adjacency from executable relationships."""
        for rel in self.relationships:
            if not rel.is_executable:
                continue

            src = rel.source_table
            tgt = rel.target_table

            # Verify tables exist in schema
            if src in self._adjacency and tgt in self._adjacency:
                self._adjacency[src].append((tgt, rel))
                self._adjacency[tgt].append((src, rel))

    def analyze_connectivity(self) -> DisconnectedAnalysisResult:
        """Perform connected component analysis over the relationship graph.

        Phase 13 rules:
        - Detect connected components.
        - Identify connected entities, disconnected entities (isolated single tables),
          and disconnected multi-table components.
        - Never automatically invent a join path for disconnected entities.
        - Disconnected entities remain valid independent entities.
        """
        visited: set[str] = set()
        components: list[list[str]] = []

        all_tables = sorted(self.schema.tables.keys())

        for table in all_tables:
            if table in visited:
                continue

            component_tables: list[str] = []
            queue = deque([table])
            visited.add(table)

            while queue:
                current = queue.popleft()
                component_tables.append(current)

                for neighbor, _ in self._adjacency.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            components.append(sorted(component_tables))

        # Sort components by size descending
        components.sort(key=lambda c: len(c), reverse=True)

        disconnected_entities: list[str] = []
        connected_entities: list[str] = []
        component_objects: list[DisconnectedComponent] = []

        for idx, comp in enumerate(components):
            is_isolated = (len(comp) == 1)
            is_main = (idx == 0 and len(comp) > 1)

            component_objects.append(
                DisconnectedComponent(
                    component_id=idx + 1,
                    tables=comp,
                    is_isolated_table=is_isolated,
                    is_main_component=is_main,
                )
            )

            if is_isolated:
                disconnected_entities.extend(comp)
            else:
                connected_entities.extend(comp)

        return DisconnectedAnalysisResult(
            connected_entities=connected_entities,
            disconnected_entities=disconnected_entities,
            disconnected_components=component_objects,
            total_tables=len(all_tables),
            connected_components_count=len(components),
        )

    def to_graph_dict(self) -> dict[str, Any]:
        """Export graph nodes and edges for visualization and semantic layer metadata."""
        connectivity = self.analyze_connectivity()

        nodes = [
            {
                "id": table_name,
                "name": table_name,
                "column_count": len(table_def.columns),
                "is_disconnected": table_name in connectivity.disconnected_entities,
            }
            for table_name, table_def in self.schema.tables.items()
        ]

        edges = [rel.to_output_dict() for rel in self.relationships]

        return {
            "nodes": nodes,
            "edges": edges,
            "connectivity": connectivity.model_dump(),
        }
