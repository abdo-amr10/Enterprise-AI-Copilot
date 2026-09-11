"""Application service for safely fixing Semantic Layer validation issues."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.semantic_layer_auto_fixer_prompt import (
    SEMANTIC_LAYER_AUTO_FIXER_PROMPT,
)
from src.application.services.semantic_layer.security.security_rule_extractor import (
    SecurityRuleExtractor,
)


class SemanticLayerAutoFixer:
    """Fix Semantic Layer validation errors without rebuilding it."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Initialize the auto-fixer."""

        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def fix(
        self,
        draft: dict[str, Any],
        validation: dict[str, Any],
        schema: dict[str, Any],
        relationships: list[dict[str, Any]],
        documentation: Any | None = None,
        security_rules: list[dict[str, Any]] | None = None,
        authoritative_security_rules: list[dict[str, Any]] | None = None,
        glossary: Any | None = None,
        sample_data: Any | None = None,
    ) -> dict[str, Any]:
        """Attempt to correct reported Semantic Layer validation errors.

        The fixer never rebuilds the Semantic Layer. It only attempts to
        correct information directly related to reported validation errors.

        Args:
            draft: Current Semantic Layer draft.
            validation: Validator result.
            schema: Authoritative database schema.
            relationships: Authoritative relationship metadata.
            documentation: Documentation source containing business and/or
                security evidence.
            security_rules: Optional normalized authoritative security/RLS
                metadata derived from Documentation.
            authoritative_security_rules: Explicit authoritative normalized
                security rules (takes precedence or extracted from documentation).
            glossary: Optional business glossary source.
            sample_data: Optional sample-data source.

        Returns:
            Corrected Semantic Layer draft with original identity preserved.
        """

        errors = validation.get("errors", [])

        if not errors:
            return deepcopy(draft)

        effective_security_rules = (
            authoritative_security_rules
            if authoritative_security_rules is not None
            else security_rules
        )
        if effective_security_rules is None and documentation is not None:
            effective_security_rules = SecurityRuleExtractor.extract_security_rules(
                documentation
            )

        prompt = self._build_prompt(
            draft=draft,
            validation=validation,
            schema=schema,
            relationships=relationships,
            documentation=documentation,
            security_rules=effective_security_rules,
            glossary=glossary,
            sample_data=sample_data,
        )

        request = GenerationRequest(
            prompt=prompt,
            format="json",
        )

        response: GenerationResponse = self._llm_client.generate(
            request
        )

        fixed_draft = self._output_parser.parse(response.text)

        return self._preserve_identity(
            original=draft,
            corrected=fixed_draft,
        )

    @staticmethod
    def _build_prompt(
        draft: dict[str, Any],
        validation: dict[str, Any],
        schema: dict[str, Any],
        relationships: list[dict[str, Any]],
        documentation: Any | None,
        security_rules: list[dict[str, Any]] | None,
        glossary: Any | None,
        sample_data: Any | None,
    ) -> str:
        """Build the auto-fixer prompt."""

        return f"""
{SEMANTIC_LAYER_AUTO_FIXER_PROMPT}

IMPORTANT IDENTITY RULES:

The following metadata fields are authoritative and MUST NOT be changed:

- semantic_layer_id
- revision_id
- base_revision_id
- trigger_type

Existing semantic-object object_id values are also authoritative.

The auto-fixer may correct semantic content only.

It MUST NOT create new identities for existing semantic objects.

CURRENT SEMANTIC LAYER:
{json.dumps(draft, indent=2, ensure_ascii=False)}

VALIDATION RESULT:
{json.dumps(validation, indent=2, ensure_ascii=False)}

AUTHORITATIVE DATABASE SCHEMA:
{json.dumps(schema, indent=2, ensure_ascii=False)}

AUTHORITATIVE DATABASE RELATIONSHIPS:
{json.dumps(relationships, indent=2, ensure_ascii=False)}

AUTHORITATIVE DOCUMENTATION:
{json.dumps(documentation, indent=2, ensure_ascii=False)}

AUTHORITATIVE NORMALIZED SECURITY RULES:
{json.dumps(security_rules, indent=2, ensure_ascii=False)}

AUTHORITATIVE BUSINESS GLOSSARY:
{json.dumps(glossary, indent=2, ensure_ascii=False)}

AUTHORITATIVE SAMPLE DATA:
{json.dumps(sample_data, indent=2, ensure_ascii=False)}
""".strip()

    @staticmethod
    def _preserve_identity(
        original: dict[str, Any],
        corrected: dict[str, Any],
    ) -> dict[str, Any]:
        """Preserve Semantic Layer, revision, and object identities."""

        result = deepcopy(corrected)

        original_metadata = original.get("metadata", {})

        if not isinstance(original_metadata, dict):
            original_metadata = {}

        corrected_metadata = result.setdefault("metadata", {})

        if not isinstance(corrected_metadata, dict):
            corrected_metadata = {}
            result["metadata"] = corrected_metadata

        for field in (
            "semantic_layer_id",
            "revision_id",
            "base_revision_id",
            "trigger_type",
        ):
            if field in original_metadata:
                corrected_metadata[field] = original_metadata[field]

        sections = (
            "entities",
            "relationships",
            "measures",
            "dimensions",
            "business_rules",
            "security_domains",
        )

        for section in sections:
            original_items = {
                item.get("name"): item
                for item in original.get(section, [])
                if (
                    isinstance(item, dict)
                    and item.get("name")
                )
            }

            corrected_items = result.get(section, [])

            if not isinstance(corrected_items, list):
                continue

            for item in corrected_items:
                if not isinstance(item, dict):
                    continue

                name = item.get("name")

                if not name:
                    continue

                original_item = original_items.get(name)

                if (
                    original_item
                    and original_item.get("object_id")
                ):
                    item["object_id"] = original_item["object_id"]

                if section == "security_domains" and original_item:
                    orig_paths = {
                        p.get("target_table"): p
                        for p in original_item.get("propagation_paths", [])
                        if isinstance(p, dict) and p.get("target_table")
                    }
                    for p in item.get("propagation_paths", []):
                        if isinstance(p, dict) and p.get("target_table") in orig_paths:
                            orig_p = orig_paths[p.get("target_table")]
                            if orig_p.get("object_id"):
                                p["object_id"] = orig_p["object_id"]

        return result

