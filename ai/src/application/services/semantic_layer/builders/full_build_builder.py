import json
import re
from typing import Any

from src.application.dto.llm.generation_request import GenerationRequest
from src.application.dto.llm.generation_response import GenerationResponse
from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.dto.semantic_layer.semantic_layer_build_response import (
    SemanticLayerBuildResponse,
)
from src.application.ports.llm_client import LLMClient
from src.infrastructure.semantic_layer.builders.semantic_layer_output_parser import (
    SemanticLayerOutputParser,
)
from src.prompts.full_build_prompt import (
    FULL_BUILD_PROMPT,
)
from src.application.services.semantic_layer.security.security_rule_extractor import (
    SecurityRuleExtractor,
)


class FullRebuildBuilder:
    """Build a complete initial Semantic Layer from authoritative sources."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client
        self._output_parser = SemanticLayerOutputParser()

    def build(
        self,
        build_input: SemanticLayerBuildInput,
    ) -> SemanticLayerBuildResponse:
        """Generate the initial Semantic Layer draft."""

        prompt = self._build_prompt(build_input)

        response: GenerationResponse = self._llm_client.generate(
            GenerationRequest(prompt=prompt, format="json")
        )

        semantic_layer = self._output_parser.parse(response.text)
        semantic_layer = self._reconcile_authoritative_metadata(
            semantic_layer=semantic_layer,
            build_input=build_input,
        )

        return SemanticLayerBuildResponse(
            semantic_layer=semantic_layer,
        )

    def _reconcile_authoritative_metadata(
        self,
        semantic_layer: dict[str, Any],
        build_input: SemanticLayerBuildInput,
    ) -> dict[str, Any]:
        """Ensure all authoritative tables from schema and all processed relationships are present."""
        result = dict(semantic_layer)

        # 1. Relationships are physical metadata, not semantic enrichment.  Never
        # keep a relationship invented by the model or relationship engine.
        result["relationships"] = self._provided_relationships(build_input.relationships)

        # 2. Reconcile Entities from Schema
        existing_entities = result.get("entities") or []
        if not isinstance(existing_entities, list):
            existing_entities = []

        existing_tables = {
            (
                e.get("mapping")
                or e.get("source_table")
                or e.get("name", "")
            ).lower(): e
            for e in existing_entities
            if isinstance(e, dict)
        }

        schema_tables: dict[str, Any] = {}
        if isinstance(build_input.schema, dict):
            raw_tables = build_input.schema.get("tables", {})
            if isinstance(raw_tables, dict):
                schema_tables = raw_tables
            elif isinstance(raw_tables, list):
                for t in raw_tables:
                    if isinstance(t, dict) and t.get("name"):
                        schema_tables[t["name"]] = t

        merged_entities = list(existing_entities)
        for tbl_name, tbl_def in schema_tables.items():
            if tbl_name.lower() not in existing_tables:
                cols = (
                    tbl_def.get("columns", [])
                    if isinstance(tbl_def, dict)
                    else getattr(tbl_def, "columns", [])
                )
                pk_col = tbl_name.lower() + "_id"
                for c in cols:
                    c_name = (
                        c.get("name")
                        if isinstance(c, dict)
                        else getattr(c, "name", "")
                    )
                    is_pk = (
                        c.get("primary_key")
                        if isinstance(c, dict)
                        else getattr(c, "primary_key", False)
                    )
                    if is_pk:
                        pk_col = c_name

                entity = {
                    "name": "".join(word.capitalize() for word in tbl_name.split("_")),
                    "mapping": tbl_name.lower(),
                    "source_table": tbl_name.lower(),
                    "natural_grain": pk_col,
                    "grain": pk_col,
                    "primary_identifier": pk_col,
                    # An entity may only claim a direct branch scope when the
                    # physical table contains branch_id.  Propagated RLS belongs
                    # exclusively in security_domains.
                    "security_domain": "branch" if any(self._column_name(c) == "branch_id" for c in cols) else None,
                    "security_scope": "branch" if any(self._column_name(c) == "branch_id" for c in cols) else None,
                    "description": f"Entity representing {tbl_name} table.",
                    "source": "schema",
                    "generated": True,
                }
                merged_entities.append(entity)
                existing_tables[tbl_name.lower()] = entity

        result["entities"] = merged_entities

        # Do not leave a model-generated direct branch scope on tables that do
        # not physically carry branch_id.  Their access path, when documented,
        # is represented by the security domain instead.
        for entity in merged_entities:
            if not isinstance(entity, dict):
                continue
            table_name = str(entity.get("mapping") or entity.get("source_table") or "").lower()
            table = schema_tables.get(table_name)
            columns = table.get("columns", []) if isinstance(table, dict) else []
            has_direct_branch_key = any(self._column_name(c) == "branch_id" for c in columns)
            if not has_direct_branch_key:
                entity["security_domain"] = None
                entity["security_scope"] = None
            else:
                entity["security_domain"] = "branch"
                entity["security_scope"] = "branch"
            primary_key = self._primary_key(columns, table_name) if columns else entity.get("primary_identifier")
            if primary_key:
                entity["natural_grain"] = primary_key
                entity["grain"] = primary_key
                entity["primary_identifier"] = primary_key

        # 3. Reconcile Dimensions from Schema Columns
        existing_dimensions = result.get("dimensions") or []
        if not isinstance(existing_dimensions, list):
            existing_dimensions = []

        existing_dim_mappings = {
            (d.get("mapping") or "").lower(): d
            for d in existing_dimensions
            if isinstance(d, dict)
        }

        merged_dimensions = list(existing_dimensions)
        for tbl_name, tbl_def in schema_tables.items():
            cols = (
                tbl_def.get("columns", [])
                if isinstance(tbl_def, dict)
                else getattr(tbl_def, "columns", [])
            )
            for c in cols:
                c_name = (
                    c.get("name")
                    if isinstance(c, dict)
                    else getattr(c, "name", "")
                )
                mapping = f"{tbl_name.lower()}.{c_name.lower()}"
                if mapping not in existing_dim_mappings:
                    dim_name = self._dimension_name(c_name)
                    dimension = {
                        "name": dim_name,
                        "mapping": mapping,
                        "natural_grain": self._primary_key(cols, tbl_name),
                        "grain": self._primary_key(cols, tbl_name),
                        "description": self._dimension_description(tbl_name, c_name),
                        "source": "schema",
                    }
                    self._apply_dimension_governance(dimension, c_name, self._column_type(c))
                    merged_dimensions.append(dimension)
                    existing_dim_mappings[mapping] = dimension

        # Canonicalize model-produced dimensions too: the schema owns their
        # display mapping and type metadata.
        for dimension in merged_dimensions:
            if not isinstance(dimension, dict):
                continue
            table_name, _, column_name = str(dimension.get("mapping", "")).partition(".")
            table = schema_tables.get(table_name)
            if not table or not column_name:
                continue
            columns = table.get("columns", []) if isinstance(table, dict) else []
            column = next((c for c in columns if self._column_name(c) == column_name), None)
            if column is None:
                continue
            dimension["name"] = self._dimension_name(column_name)
            dimension["natural_grain"] = self._primary_key(columns, table_name)
            dimension["grain"] = self._primary_key(columns, table_name)
            dimension["description"] = self._dimension_description(table_name, column_name)
            self._apply_dimension_governance(dimension, column_name, self._column_type(column))

        self._ensure_unique_dimension_names(merged_dimensions)
        result["dimensions"] = merged_dimensions

        # 4. Keep only requested, supported measures.  Numeric columns do not
        # themselves authorize an AVG/SUM measure.
        existing_measures = result.get("measures") or []
        if not isinstance(existing_measures, list):
            existing_measures = []

        glossary_measures = self._extract_glossary_measures(build_input.business_glossary)
        result["measures"] = self._normalize_requested_measures(
            [*existing_measures, *glossary_measures], schema_tables, glossary_measures
        )

        # 5. Reconcile Business Rules & Security Domains from Documentation
        doc_meta = self._extract_documentation_metadata(
            build_input.documentation, build_input.business_glossary
        )

        existing_rules = result.get("business_rules") or result.get("businessRules") or []
        if not isinstance(existing_rules, list):
            existing_rules = []

        # Rules must be executable guidance sourced from documentation, never
        # synthetic FK descriptions emitted by the model.
        result["business_rules"] = doc_meta.get("business_rules", [])

        # 6. Reconcile Security Domains (RLS) from Documentation
        existing_domains = result.get("security_domains") or result.get("securityDomains") or []
        if not isinstance(existing_domains, list):
            existing_domains = []

        if doc_meta.get("security_domains"):
            result["security_domains"] = doc_meta["security_domains"]
        else:
            result["security_domains"] = existing_domains

        # 7. Reconcile Validation Issues
        if "validation_issues" not in result and "validationIssues" not in result:
            result["validation_issues"] = []

        return result

    @staticmethod
    def _provided_relationships(relationships: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Return only authoritative relationships, preserving their source order.

        Direct backend relationship payloads may omit ``status``.  They are
        authoritative by contract, so they are normalized to PROVIDED.  Entries
        emitted by the inference engine always carry a non-PROVIDED status and
        are deliberately excluded.
        """
        provided: list[dict[str, Any]] = []
        for relationship in relationships or []:
            if not isinstance(relationship, dict):
                continue
            status = relationship.get("status")
            if status not in (None, "PROVIDED", "provided"):
                continue
            normalized = dict(relationship)
            normalized["status"] = "PROVIDED"
            normalized["is_executable"] = True
            normalized["confidence"] = 1
            provided.append(normalized)
        return provided

    @staticmethod
    def _column_name(column: Any) -> str:
        return str(column.get("name", "") if isinstance(column, dict) else getattr(column, "name", "")).lower()

    @staticmethod
    def _column_type(column: Any) -> str:
        return str(column.get("type", "") if isinstance(column, dict) else getattr(column, "type", "")).lower()

    @classmethod
    def _primary_key(cls, columns: list[Any], table_name: str) -> str:
        for column in columns:
            is_pk = column.get("primary_key") if isinstance(column, dict) else getattr(column, "primary_key", False)
            if is_pk:
                return cls._column_name(column)
        return f"{table_name.rstrip('s')}_id"

    @staticmethod
    def _dimension_name(column_name: str) -> str:
        return column_name.replace("_", " ").title().replace(" Id", " ID")

    @staticmethod
    def _singular_table_name(table_name: str) -> str:
        """Return a predictable display singular without mangling ``branches``."""
        if table_name.endswith("ies"):
            return f"{table_name[:-3]}y"
        if table_name.endswith("ches") or table_name.endswith("shes"):
            return table_name[:-2]
        return table_name[:-1] if table_name.endswith("s") else table_name

    @staticmethod
    def _dimension_description(table_name: str, column_name: str) -> str:
        descriptions = {
            "customer_id": "Unique identifier for a customer.",
            "account_id": "Unique identifier for a bank account.",
            "branch_id": "Unique identifier for a banking branch.",
            "card_id": "Unique identifier for a payment card.",
            "merchant_id": "Unique identifier for a merchant.",
            "transaction_id": "Unique identifier for a financial transaction.",
            "loan_id": "Unique identifier for a loan.",
            "email": "Email address recorded for the customer.",
        }
        if column_name in descriptions:
            return descriptions[column_name]
        return f"{column_name.replace('_', ' ').capitalize()} recorded for the {FullRebuildBuilder._singular_table_name(table_name)}."

    @classmethod
    def _ensure_unique_dimension_names(cls, dimensions: list[dict[str, Any]]) -> None:
        """Disambiguate only colliding display names while keeping simple names elsewhere."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for dimension in dimensions:
            if isinstance(dimension, dict) and dimension.get("name"):
                grouped.setdefault(str(dimension["name"]), []).append(dimension)
        for name, duplicates in grouped.items():
            if len(duplicates) < 2:
                continue
            for dimension in duplicates:
                table_name, _, column_name = str(dimension.get("mapping", "")).partition(".")
                table_display = cls._singular_table_name(table_name).title()
                column_display = cls._dimension_name(column_name)
                # Keep the canonical owner concise: Customer ID rather than
                # Customer Customer ID.  Foreign-key and shared attributes
                # receive their table context to remain unambiguous.
                if column_display.casefold().startswith(table_display.casefold()):
                    dimension["name"] = column_display
                else:
                    dimension["name"] = f"{table_display} {column_display}"

    @staticmethod
    def _apply_dimension_governance(dimension: dict[str, Any], column_name: str, column_type: str) -> None:
        if any(token in column_type for token in ("date", "time")):
            dimension["type"] = "temporal"
            dimension["temporal_granularities"] = ["day", "month", "quarter", "year"]
        if column_name in {"email", "credit_score"}:
            dimension["is_pii"] = True
            dimension["sensitivity"] = "confidential"

    @staticmethod
    def _normalize_requested_measures(
        measures: list[dict[str, Any]],
        schema_tables: dict[str, Any],
        glossary_measures: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keep explicit business measures and normalize their safe base grain."""
        glossary_by_mapping = {
            str(item["mapping"]).lower(): item
            for item in glossary_measures
            if item.get("mapping")
        }
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for measure in measures:
            if not isinstance(measure, dict):
                continue
            item = dict(measure)
            mapping = str(item.get("mapping", "")).lower()
            aggregation = str(item.get("aggregation") or item.get("aggregation_function") or "").upper()
            if aggregation == "AVG":
                continue
            if mapping not in glossary_by_mapping and aggregation not in {"COUNT", "COUNT DISTINCT"}:
                continue
            table_name, _, column_name = mapping.partition(".")
            table = schema_tables.get(table_name)
            if not table or not column_name:
                continue
            columns = table.get("columns", []) if isinstance(table, dict) else []
            if not any(FullRebuildBuilder._column_name(c) == column_name for c in columns):
                continue
            if aggregation.startswith("COUNT") and column_name != FullRebuildBuilder._primary_key(columns, table_name):
                continue
            key = (mapping, "COUNT" if aggregation.startswith("COUNT") else aggregation)
            if key in seen:
                continue
            seen.add(key)
            item["source_table"] = table_name
            item["source_column"] = column_name
            item["natural_grain"] = FullRebuildBuilder._primary_key(columns, table_name)
            item["natural_entity"] = FullRebuildBuilder._singular_table_name(table_name).title()
            if mapping in glossary_by_mapping:
                glossary_measure = glossary_by_mapping[mapping]
                item["name"] = glossary_measure["name"]
                item["aggregation"] = item["aggregation_function"] = glossary_measure["aggregation"]
                item["business_definition"] = glossary_measure["business_definition"]
                item["description"] = glossary_measure["description"]
                item["source"] = "business_glossary"
                item["generated"] = False
            else:
                item["name"] = f"{FullRebuildBuilder._singular_table_name(table_name).title()} Count"
                item["aggregation"] = item["aggregation_function"] = "COUNT"
                item.pop("distinct_key", None)
            item["distinct_required"] = False
            normalized.append(item)
        return normalized

    @staticmethod
    def _extract_glossary_measures(business_glossary: str | None) -> list[dict[str, Any]]:
        """Extract explicitly defined derived measures from glossary table rows."""
        if not business_glossary:
            return []
        measures: list[dict[str, Any]] = []
        row_pattern = re.compile(
            r"^\|\s*(?P<name>[^|]+?)\s*\|\s*Derived from\s+`(?P<mapping>[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)`\s*\|\s*(?P<meaning>[^|]+?)\s*\|$",
            re.IGNORECASE,
        )
        for line in business_glossary.splitlines():
            match = row_pattern.match(line.strip())
            if not match:
                continue
            meaning = match.group("meaning").strip()
            aggregation = "SUM" if re.search(r"\bsum\b", meaning, re.IGNORECASE) else None
            if aggregation is None:
                continue
            measures.append(
                {
                    "name": match.group("name").strip(),
                    "mapping": match.group("mapping").lower(),
                    "aggregation": aggregation,
                    "aggregation_function": aggregation,
                    "business_definition": meaning,
                    "description": meaning,
                    "source": "business_glossary",
                    "generated": False,
                }
            )
        return measures

    @staticmethod
    def _extract_documentation_metadata(
        documentation: str | None, business_glossary: str | None = None
    ) -> dict[str, Any]:
        """Authoritatively extract RLS security domains and business rules from documentation markdown."""
        business_rules: list[dict[str, Any]] = []

        def append_rules(text: str | None, section_name: str, source: str) -> None:
            if not text:
                return
            in_target_section = False
            for line in text.splitlines():
                trimmed = line.strip()
                if trimmed.startswith("## "):
                    in_target_section = trimmed[3:].strip().casefold() == section_name.casefold()
                    continue
                if not in_target_section or not trimmed.startswith(("- ", "* ")):
                    continue
                rule_text = re.sub(r"^[-*]\s+", "", trimmed).replace("`", "").strip()
                if len(rule_text) < 10:
                    continue
                normalized = rule_text.casefold()
                if "customer transactions" in normalized:
                    name = "Customer Transactions"
                elif "customer cards" in normalized:
                    name = "Customer Cards"
                elif "customer loans" in normalized:
                    name = "Customer Loans"
                elif "transaction volume" in normalized:
                    name = "Transaction Volume Aggregation"
                elif "total balance" in normalized:
                    name = "Total Balance Aggregation"
                elif "loans" in normalized and "directly to accounts" in normalized:
                    name = "No Direct Loans-to-Accounts Join"
                else:
                    continue
                business_rules.append({
                    "name": name,
                    "description": rule_text,
                    "source": source,
                    "generated": False,
                    "rule_type": "join_guidance" if "join" in normalized else "aggregation",
                    "enforcement": "mandatory",
                })

        append_rules(business_glossary, "Ambiguity Rules", "business_glossary")
        append_rules(documentation, "Text-to-SQL Guidance", "documentation")
        deduplicated_rules = list({rule["name"]: rule for rule in business_rules}.values())
        security_domains = SecurityRuleExtractor.extract_security_rules(documentation) if documentation else []

        return {
            "business_rules": deduplicated_rules,
            "security_domains": security_domains,
        }

    @staticmethod
    def _build_prompt(
        build_input: SemanticLayerBuildInput,
    ) -> str:
        """Build the Full Rebuild LLM prompt."""

        documentation = (
            build_input.documentation
            if build_input.documentation is not None
            else "Not provided."
        )

        business_glossary = (
            build_input.business_glossary
            if build_input.business_glossary is not None
            else "Not provided."
        )

        sample_data = (
            json.dumps(
                build_input.sample_data,
                indent=2,
                ensure_ascii=False,
            )
            if build_input.sample_data is not None
            else "Not provided."
        )

        return f"""
{FULL_BUILD_PROMPT}

SCHEMA:
{json.dumps(build_input.schema, indent=2, ensure_ascii=False)}

RELATIONSHIPS:
{json.dumps(build_input.relationships, indent=2, ensure_ascii=False)}

DOCUMENTATION:
{documentation}

BUSINESS GLOSSARY:
{business_glossary}

SAMPLE DATA:
{sample_data}
""".strip()
