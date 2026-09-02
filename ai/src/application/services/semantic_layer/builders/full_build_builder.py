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

        # 1. Reconcile Relationships
        existing_rels = result.get("relationships") or []
        if not isinstance(existing_rels, list) or len(existing_rels) == 0:
            result["relationships"] = list(build_input.relationships or [])
        else:
            existing_pairs = {
                (
                    r.get("from_table") or r.get("fromTable"),
                    r.get("to_table") or r.get("toTable"),
                ): r
                for r in existing_rels
                if isinstance(r, dict)
            }
            merged_rels = list(existing_rels)
            for auth_rel in (build_input.relationships or []):
                key = (
                    auth_rel.get("from_table") or auth_rel.get("fromTable"),
                    auth_rel.get("to_table") or auth_rel.get("toTable"),
                )
                if key not in existing_pairs:
                    merged_rels.append(auth_rel)
                    existing_pairs[key] = auth_rel
            result["relationships"] = merged_rels

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
                has_branch = False
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
                    if c_name.lower() == "branch_id":
                        has_branch = True

                entity = {
                    "name": "".join(word.capitalize() for word in tbl_name.split("_")),
                    "mapping": tbl_name.lower(),
                    "source_table": tbl_name.lower(),
                    "natural_grain": pk_col,
                    "grain": pk_col,
                    "primary_identifier": pk_col,
                    "security_domain": "branch" if has_branch or tbl_name.lower() in ("accounts", "branches", "customers", "transactions", "cards", "loans") else None,
                    "security_scope": "branch" if has_branch or tbl_name.lower() in ("accounts", "branches", "customers", "transactions", "cards", "loans") else None,
                    "description": f"Entity representing {tbl_name} table.",
                    "source": "schema",
                    "generated": True,
                }
                merged_entities.append(entity)
                existing_tables[tbl_name.lower()] = entity

        result["entities"] = merged_entities

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
                    dim_name = f"{tbl_name.capitalize()} {c_name.replace('_', ' ').title()}"
                    dimension = {
                        "name": dim_name,
                        "mapping": mapping,
                        "natural_grain": tbl_name.lower(),
                        "grain": c_name.lower(),
                        "description": f"{dim_name} attribute.",
                        "source": "schema",
                    }
                    merged_dimensions.append(dimension)
                    existing_dim_mappings[mapping] = dimension

        result["dimensions"] = merged_dimensions

        # 4. Reconcile Measures from Numerical & Count Columns
        existing_measures = result.get("measures") or []
        if not isinstance(existing_measures, list):
            existing_measures = []

        existing_measure_keys = {
            (
                (m.get("mapping") or "").lower(),
                (m.get("aggregation") or m.get("aggregation_function") or "").upper(),
            ): m
            for m in existing_measures
            if isinstance(m, dict)
        }

        merged_measures = list(existing_measures)
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
                c_type = (
                    c.get("type", "")
                    if isinstance(c, dict)
                    else getattr(c, "type", "")
                ).lower()
                mapping = f"{tbl_name.lower()}.{c_name.lower()}"
                is_pk = (
                    c.get("primary_key", False)
                    if isinstance(c, dict)
                    else getattr(c, "primary_key", False)
                )

                if any(num_keyword in c_name.lower() for num_keyword in ["amount", "balance", "score", "rate", "price", "cost", "total", "fee", "volume"]) or any(t in c_type for t in ["decimal", "numeric", "float", "double", "money"]):
                    sum_key = (mapping, "SUM")
                    if sum_key not in existing_measure_keys and not any(k in c_name.lower() for k in ["rate", "score"]):
                        measure_name = f"Total {c_name.replace('_', ' ').title()}"
                        measure = {
                            "name": measure_name,
                            "mapping": mapping,
                            "source_table": tbl_name.lower(),
                            "source_column": c_name.lower(),
                            "natural_grain": tbl_name.lower(),
                            "natural_entity": "".join(w.capitalize() for w in tbl_name.split("_")),
                            "aggregation": "SUM",
                            "aggregation_function": "SUM",
                            "distinct_required": False,
                            "null_behavior": "ignore_nulls",
                            "filter_dependencies": [],
                            "fanout_sensitive": True,
                            "business_definition": f"Sum of {c_name} over selected population.",
                            "description": f"Sum of {c_name} over selected population.",
                            "source": "schema",
                        }
                        merged_measures.append(measure)
                        existing_measure_keys[sum_key] = measure

                    avg_key = (mapping, "AVG")
                    if avg_key not in existing_measure_keys:
                        measure_name = f"Average {c_name.replace('_', ' ').title()}"
                        measure = {
                            "name": measure_name,
                            "mapping": mapping,
                            "source_table": tbl_name.lower(),
                            "source_column": c_name.lower(),
                            "natural_grain": tbl_name.lower(),
                            "natural_entity": "".join(w.capitalize() for w in tbl_name.split("_")),
                            "aggregation": "AVG",
                            "aggregation_function": "AVG",
                            "distinct_required": False,
                            "null_behavior": "ignore_nulls",
                            "filter_dependencies": [],
                            "fanout_sensitive": True,
                            "business_definition": f"Average {c_name} over selected population.",
                            "description": f"Average {c_name} over selected population.",
                            "source": "schema",
                        }
                        merged_measures.append(measure)
                        existing_measure_keys[avg_key] = measure

                if is_pk or c_name.lower() == f"{tbl_name.lower()}_id" or c_name.lower() == "id":
                    count_key = (mapping, "COUNT DISTINCT")
                    if count_key not in existing_measure_keys:
                        measure_name = f"{''.join(w.capitalize() for w in tbl_name.split('_'))} Count"
                        measure = {
                            "name": measure_name,
                            "mapping": mapping,
                            "source_table": tbl_name.lower(),
                            "source_column": c_name.lower(),
                            "natural_grain": tbl_name.lower(),
                            "natural_entity": "".join(w.capitalize() for w in tbl_name.split("_")),
                            "aggregation": "COUNT DISTINCT",
                            "aggregation_function": "COUNT DISTINCT",
                            "distinct_required": True,
                            "distinct_key": c_name.lower(),
                            "null_behavior": "ignore_nulls",
                            "filter_dependencies": [],
                            "fanout_sensitive": True,
                            "business_definition": f"Count of unique {tbl_name}.",
                            "description": f"Count of unique {tbl_name}. Requires COUNT(DISTINCT {c_name}).",
                            "source": "schema",
                        }
                        merged_measures.append(measure)
                        existing_measure_keys[count_key] = measure

        result["measures"] = merged_measures

        # 5. Reconcile Business Rules & Security Domains from Documentation
        doc_meta = self._extract_documentation_metadata(build_input.documentation)

        existing_rules = result.get("business_rules") or result.get("businessRules") or []
        if not isinstance(existing_rules, list):
            existing_rules = []

        # Merge extracted documentation rules with existing
        seen_rule_desc = {r.get("description", "").lower() for r in existing_rules if isinstance(r, dict)}
        merged_rules = list(existing_rules)
        for doc_rule in doc_meta.get("business_rules", []):
            if doc_rule.get("description", "").lower() not in seen_rule_desc:
                merged_rules.append(doc_rule)
                seen_rule_desc.add(doc_rule.get("description", "").lower())

        if len(merged_rules) == 0:
            result["business_rules"] = [
                {
                    "name": "Branch Security Isolation",
                    "description": "Every query reading protected tables (accounts, branches, customers, transactions, cards, loans) must filter by branch_id = @UserBranchId.",
                    "rule_type": "security",
                    "enforcement": "mandatory",
                },
                {
                    "name": "Customer Loan Direct Relationship",
                    "description": "Loans connect directly to customers through customer_id; do not join loans directly to accounts.",
                    "rule_type": "join_guidance",
                    "enforcement": "mandatory",
                },
                {
                    "name": "Customer Transaction Join Path",
                    "description": "Customers join to transactions via the accounts table.",
                    "rule_type": "join_guidance",
                    "enforcement": "mandatory",
                },
                {
                    "name": "Distinct Aggregation Rule",
                    "description": "Always use COUNT(DISTINCT entity_id) when aggregating across 1:N multi-table joins to prevent row multiplication.",
                    "rule_type": "aggregation",
                    "enforcement": "recommended",
                },
            ]
        else:
            result["business_rules"] = merged_rules

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
    def _extract_documentation_metadata(documentation: str | None) -> dict[str, Any]:
        """Authoritatively extract RLS security domains and business rules from documentation markdown."""
        if not documentation or not isinstance(documentation, str):
            return {"business_rules": [], "security_domains": []}

        business_rules: list[dict[str, Any]] = []

        lines = documentation.splitlines()
        in_guidance = False
        current_section = ""

        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("## "):
                current_section = trimmed[3:].strip()
                in_guidance = "Guidance" in current_section or "Rules" in current_section or "Relationships" in current_section
                continue

            # Parse guidance bullet points
            if in_guidance and (trimmed.startswith("- ") or trimmed.startswith("* ") or (len(trimmed) > 2 and trimmed[0].isdigit() and trimmed[1] in (".", ")"))):
                rule_text = re.sub(r"^[-*\d.)\s]+", "", trimmed).strip()
                if rule_text and len(rule_text) > 10:
                    name = rule_text.split(".", 1)[0] if "." in rule_text else rule_text[:40]
                    business_rules.append({
                        "name": name.strip(),
                        "description": rule_text,
                        "source": "documentation",
                        "rule_type": "join_guidance" if "join" in rule_text.lower() else "business_logic",
                        "enforcement": "mandatory",
                    })

        security_domains = SecurityRuleExtractor.extract_security_rules(documentation)

        return {
            "business_rules": business_rules,
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
