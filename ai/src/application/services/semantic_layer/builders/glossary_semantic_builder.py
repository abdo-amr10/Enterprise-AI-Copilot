import json
import logging
import re
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.semantic_sub_prompts import GLOSSARY_SEMANTIC_PROMPT

logger = logging.getLogger(__name__)


class GlossarySemanticBuilder:
    """Sub-builder responsible for extracting measures, metrics, and business rules from the glossary."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def extract(
        self,
        business_glossary: str | None,
        schema_tables: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract measures and business rules using deterministic parsing with LLM enrichment."""
        if not business_glossary or not business_glossary.strip():
            return {"measures": [], "business_rules": []}

        # 1. Deterministic baseline extraction
        det_measures = self._extract_deterministic_measures(business_glossary)
        det_rules = self._extract_deterministic_rules(business_glossary)

        if self._llm_client is None:
            return {"measures": det_measures, "business_rules": det_rules}

        # 2. Focused LLM enrichment for unstructured or complex metrics
        valid_cols = []
        for tbl_name, tbl_def in schema_tables.items():
            cols = (
                tbl_def.get("columns", [])
                if isinstance(tbl_def, dict)
                else getattr(tbl_def, "columns", [])
            )
            for c in cols:
                c_name = c.get("name") if isinstance(c, dict) else getattr(c, "name", "")
                if c_name:
                    valid_cols.append(f"{tbl_name.lower()}.{c_name.lower()}")

        prompt = f"""{GLOSSARY_SEMANTIC_PROMPT}

SCHEMA COLUMNS:
{json.dumps(valid_cols[:150], indent=2, ensure_ascii=False)}

BUSINESS GLOSSARY:
{business_glossary}
""".strip()

        try:
            response: GenerationResponse = self._llm_client.generate(
                GenerationRequest(prompt=prompt, format="json")
            )
            parsed = self._output_parser.parse(response.text)
            llm_measures = parsed.get("measures") or []
            llm_rules = parsed.get("business_rules") or []

            combined_measures = self._merge_measures(det_measures, llm_measures, valid_cols)
            combined_rules = self._merge_rules(det_rules, llm_rules)
            return {"measures": combined_measures, "business_rules": combined_rules}
        except Exception as err:
            logger.warning(
                "GlossarySemanticBuilder LLM extraction failed (%s); using deterministic extraction.",
                err,
            )

        return {"measures": det_measures, "business_rules": det_rules}

    @staticmethod
    def _extract_deterministic_measures(business_glossary: str) -> list[dict[str, Any]]:
        """Parse structured markdown glossary tables for metrics."""
        measures = []
        lines = business_glossary.splitlines()
        for line in lines:
            if not line.strip().startswith("|") or line.strip().startswith("|---"):
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) < 3 or cells[0].lower() in {"term", "business term"}:
                continue

            term, mapping, meaning = cells[0], cells[1], cells[2]
            clean_term = term.strip("`*")
            clean_mapping = mapping.replace("Derived from", "").strip(" `*")
            text = f"{term} {meaning}".lower()

            if any(k in text for k in ("average", "avg", "mean")):
                agg = "AVG"
            elif any(k in text for k in ("sum", "total", "volume", "balance")):
                agg = "SUM"
            elif any(k in text for k in ("count", "number of")):
                agg = "COUNT"
            elif "maximum" in text or "max" in text:
                agg = "MAX"
            elif "minimum" in text or "min" in text:
                agg = "MIN"
            else:
                agg = "SUM"

            if "." in clean_mapping:
                measures.append({
                    "name": clean_term,
                    "mapping": clean_mapping,
                    "aggregation": agg,
                    "description": meaning.strip("`*"),
                })
        return measures

    @staticmethod
    def _extract_deterministic_rules(business_glossary: str) -> list[dict[str, Any]]:
        """Extract ambiguity and calculation rules from the glossary."""
        rules = []
        in_section = False
        for line in business_glossary.splitlines():
            sline = line.strip()
            if sline.startswith("## Ambiguity Rules") or sline.startswith("## Business Rules"):
                in_section = True
                continue
            elif sline.startswith("## ") and in_section:
                in_section = False
                continue

            if in_section and sline.startswith("-"):
                rule_text = sline.lstrip("- *").strip()
                name_match = re.search(r"\*\*([^*]+)\*\*", rule_text)
                rule_name = name_match.group(1).title() if name_match else "Business Rule"
                rules.append({
                    "name": rule_name,
                    "description": rule_text.replace("**", "").strip(),
                    "source": "business_glossary",
                    "generated": False,
                    "rule_type": "join_guidance" if "join" in rule_text.lower() else "business_guidance",
                    "enforcement": "mandatory",
                })
        return rules

    @staticmethod
    def _merge_measures(
        det_measures: list[dict[str, Any]],
        llm_measures: list[dict[str, Any]],
        valid_cols: list[str],
    ) -> list[dict[str, Any]]:
        """Merge and validate measures from both sources."""
        seen_names = set()
        result = []
        for m in det_measures:
            seen_names.add(m["name"].lower())
            result.append(m)

        for m in llm_measures:
            if not isinstance(m, dict):
                continue
            name = m.get("name")
            mapping = str(m.get("mapping", "")).lower()
            if not name or name.lower() in seen_names:
                continue
            # Ensure mapping is a valid column or expression
            if mapping in valid_cols or "." in mapping:
                seen_names.add(name.lower())
                result.append(m)

        return result

    @staticmethod
    def _merge_rules(
        det_rules: list[dict[str, Any]],
        llm_rules: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge business rules without duplicates."""
        seen_names = set()
        result = []
        for r in det_rules:
            seen_names.add(r["name"].lower())
            result.append(r)

        for r in llm_rules:
            if not isinstance(r, dict):
                continue
            name = r.get("name")
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            result.append(r)

        return result
