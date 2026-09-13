import json
import logging
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.semantic_sub_prompts import RELATIONSHIP_SEMANTIC_PROMPT

logger = logging.getLogger(__name__)


class RelationshipSemanticEnricher:
    """Sub-enricher responsible for adding business semantic notes and join intents to relationships."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def enrich(
        self,
        relationships: list[dict[str, Any]],
        documentation: str | None = None,
    ) -> list[dict[str, Any]]:
        """Enrich authoritative physical relationships with business context and descriptions."""
        if not relationships:
            return []

        # If no LLM or no join guidance exists, apply basic deterministic descriptions
        if self._llm_client is None:
            return self._apply_deterministic_descriptions(relationships)

        # Filter and compact relationships for prompt efficiency
        compact_rels = [
            {
                "from_table": r.get("from_table") or r.get("source_table"),
                "to_table": r.get("to_table") or r.get("target_table"),
                "from_column": r.get("from_column") or r.get("source_column"),
                "to_column": r.get("to_column") or r.get("target_column"),
            }
            for r in relationships
            if isinstance(r, dict)
        ]

        doc_text = documentation if documentation is not None else "Not provided."
        prompt = f"""{RELATIONSHIP_SEMANTIC_PROMPT}

RELATIONSHIPS:
{json.dumps(compact_rels, indent=2, ensure_ascii=False)}

DOCUMENTATION:
{doc_text}
""".strip()

        try:
            response: GenerationResponse = self._llm_client.generate(
                GenerationRequest(prompt=prompt, format="json")
            )
            parsed = self._output_parser.parse(response.text)
            enriched_items = parsed.get("relationships")
            if isinstance(enriched_items, list) and enriched_items:
                return self._merge_enriched_data(relationships, enriched_items)
        except Exception as err:
            logger.warning(
                "RelationshipSemanticEnricher LLM generation failed (%s); retaining base relationships.",
                err,
            )

        return self._apply_deterministic_descriptions(relationships)

    @staticmethod
    def _apply_deterministic_descriptions(
        relationships: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Ensure every relationship has at least a clean deterministic description."""
        result = []
        for r in relationships:
            item = dict(r)
            if not item.get("description"):
                from_tbl = str(item.get("from_table") or "").replace("_", " ").title()
                to_tbl = str(item.get("to_table") or "").replace("_", " ").title()
                item["description"] = f"Relates {from_tbl} records to their corresponding {to_tbl}."
            result.append(item)
        return result

    @staticmethod
    def _merge_enriched_data(
        authoritative: list[dict[str, Any]],
        enriched: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge LLM-generated business descriptions into authoritative relationships."""
        enriched_map: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        for item in enriched:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("from_table", "")).lower(),
                str(item.get("from_column", "")).lower(),
                str(item.get("to_table", "")).lower(),
                str(item.get("to_column", "")).lower(),
            )
            if all(key):
                enriched_map[key] = item

        result = []
        for rel in authoritative:
            item = dict(rel)
            key = (
                str(item.get("from_table", "")).lower(),
                str(item.get("from_column", "")).lower(),
                str(item.get("to_table", "")).lower(),
                str(item.get("to_column", "")).lower(),
            )
            if key in enriched_map:
                llm_meta = enriched_map[key]
                if llm_meta.get("description"):
                    item["description"] = llm_meta["description"]
                if llm_meta.get("join_intent"):
                    item["join_intent"] = llm_meta["join_intent"]
            elif not item.get("description"):
                from_tbl = str(item.get("from_table") or "").replace("_", " ").title()
                to_tbl = str(item.get("to_table") or "").replace("_", " ").title()
                item["description"] = f"Relates {from_tbl} records to their corresponding {to_tbl}."
            result.append(item)
        return result
