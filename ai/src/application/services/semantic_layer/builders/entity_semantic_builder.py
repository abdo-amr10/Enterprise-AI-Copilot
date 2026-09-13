import json
import logging
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.semantic_sub_prompts import ENTITY_SEMANTIC_PROMPT

logger = logging.getLogger(__name__)


class EntitySemanticBuilder:
    """Sub-builder responsible for enriching physical tables with semantic business metadata."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()
        self.last_parsed: dict[str, Any] = {}

    def build(
        self,
        schema: dict[str, Any],
        documentation: str | None = None,
        business_glossary: str | None = None,
        relationships: list[dict[str, Any]] | None = None,
        sample_data: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Generate semantic metadata (names, descriptions, synonyms) for database entities."""
        self.last_parsed = {}
        schema_tables = self._extract_tables(schema)
        if not schema_tables:
            return []

        # If no LLM client is available, fallback immediately to deterministic metadata.
        if self._llm_client is None:
            return self._build_deterministic_entities(schema_tables)

        prompt = self._build_prompt(
            schema=schema,
            schema_tables=schema_tables,
            documentation=documentation,
            business_glossary=business_glossary,
            relationships=relationships,
            sample_data=sample_data,
        )

        try:
            response: GenerationResponse = self._llm_client.generate(
                GenerationRequest(prompt=prompt, format="json")
            )
            parsed = self._output_parser.parse(response.text)
            self.last_parsed = parsed if isinstance(parsed, dict) else {}
            entities = self.last_parsed.get("entities")
            if isinstance(entities, list) and entities:
                return entities
        except Exception as err:
            logger.warning(
                "EntitySemanticBuilder LLM generation failed (%s); falling back to deterministic entities.",
                err,
            )
            self.last_parsed = {}

        return self._build_deterministic_entities(schema_tables)

    @staticmethod
    def _extract_tables(schema: dict[str, Any]) -> dict[str, Any]:
        """Normalize schema tables to a standard dictionary."""
        if not isinstance(schema, dict):
            return {}
        raw = schema.get("tables", {})
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            result = {}
            for t in raw:
                if isinstance(t, dict) and t.get("name"):
                    result[t["name"]] = t
            return result
        return {}

    @classmethod
    def _build_deterministic_entities(cls, schema_tables: dict[str, Any]) -> list[dict[str, Any]]:
        """Fallback deterministic entity metadata generator."""
        entities = []
        for tbl_name, tbl_def in schema_tables.items():
            clean_name = "".join(word.capitalize() for word in tbl_name.split("_"))
            cols = (
                tbl_def.get("columns", [])
                if isinstance(tbl_def, dict)
                else getattr(tbl_def, "columns", [])
            )
            pk = tbl_name.lower() + "_id"
            for c in cols:
                c_name = c.get("name") if isinstance(c, dict) else getattr(c, "name", "")
                is_pk = c.get("primary_key") if isinstance(c, dict) else getattr(c, "primary_key", False)
                if is_pk:
                    pk = c_name
                    break

            entities.append({
                "mapping": tbl_name.lower(),
                "name": clean_name,
                "description": f"Entity representing {tbl_name.replace('_', ' ').title()} table.",
                "natural_grain": pk,
                "grain": pk,
                "primary_identifier": pk,
                "source": "schema",
                "generated": True,
            })
        return entities

    @classmethod
    def _build_prompt(
        cls,
        schema: dict[str, Any],
        schema_tables: dict[str, Any],
        documentation: str | None,
        business_glossary: str | None,
        relationships: list[dict[str, Any]] | None,
        sample_data: Any | None,
    ) -> str:
        """Construct the compact entity prompt with necessary context."""
        # Build compact schema representation
        compact_tables = []
        for tbl_name, tbl_def in schema_tables.items():
            cols = (
                tbl_def.get("columns", [])
                if isinstance(tbl_def, dict)
                else getattr(tbl_def, "columns", [])
            )
            col_summaries = []
            for c in cols:
                c_name = c.get("name") if isinstance(c, dict) else getattr(c, "name", "")
                is_pk = c.get("primary_key") if isinstance(c, dict) else getattr(c, "primary_key", False)
                if is_pk:
                    col_summaries.append(f"{c_name} (PK)")
                else:
                    col_summaries.append(c_name)
            compact_tables.append({
                "table": tbl_name,
                "columns": col_summaries,
            })

        doc_text = documentation if documentation is not None else "Not provided."
        glossary_text = business_glossary if business_glossary is not None else "Not provided."
        rel_text = (
            json.dumps(relationships, indent=2, ensure_ascii=False)
            if relationships is not None
            else "Not provided."
        )
        sample_text = (
            json.dumps(sample_data, indent=2, ensure_ascii=False)
            if sample_data is not None
            else "Not provided."
        )

        return f"""{ENTITY_SEMANTIC_PROMPT}

SCHEMA:
{json.dumps(compact_tables, indent=2, ensure_ascii=False)}

RELATIONSHIPS:
{rel_text}

DOCUMENTATION:
{doc_text}

BUSINESS GLOSSARY:
{glossary_text}

SAMPLE DATA:
{sample_text}
""".strip()
