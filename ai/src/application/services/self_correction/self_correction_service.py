"""Orchestrates Hybrid Self-Correction for a generated SQL query.

Execution Hierarchy:
    generated SQL
        -> Syntax Validator (Deterministic)
        -> Schema Validator (Deterministic)
        -> Relationship Validator (Deterministic)
        -> RLS Validator (Deterministic)
        -> [If issues exist] Deterministic Repair Layer (AST-based)
        -> Re-Validate Deterministically
        -> [Only if all pass] SQL Critic (LLM, diagnosis only)
        -> CriticFindingVerifier (Deterministic - filters hallucinated findings)
        -> [Only if issues remain] SQL Correction (LLM, fixes only those issues)
        -> Candidate Fingerprint & Oscillation Detection (A -> B -> A)
        -> Re-validate from the top
        -> up to max_attempts corrections, then FAILED
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any
import sqlglot

from src.application.ports.physical_schema_repository import PhysicalSchemaRepository
from src.application.services.self_correction.critic_finding_verifier import (
    CriticFindingVerifier,
)
from src.application.dto.self_correction.self_correction_outcome import (
    SelfCorrectionOutcome,
)
from src.application.dto.self_correction.validation_issue import ValidationIssue
from src.application.services.self_correction.sql_correction_service import SQLCorrectionService
from src.application.services.self_correction.sql_critic_service import SQLCriticService
from src.application.services.self_correction.validators.sql_relationship_validator import (
    SQLRelationshipValidator,
)
from src.application.services.self_correction.validators.sql_schema_validator import (
    SQLSchemaValidator,
)
from src.application.services.self_correction.validators.sql_syntax_validator import (
    SQLSyntaxValidator,
)
from src.application.services.self_correction.validators.sql_rls_validator import SQLRlsValidator
from src.application.services.self_correction.sql_deterministic_repair_service import (
    SQLDeterministicRepairService,
)
from src.application.services.context_retrieval.context_retrieval_service import (
    ContextRetrievalService,
)
from src.observability.latency_audit import stage

logger = logging.getLogger(__name__)

TraceObserver = Callable[[dict[str, Any]], None]


def compute_sql_fingerprint(sql: str) -> str:
    """Compute normalized semantic fingerprint for AST-based equivalence."""
    if not sql or not sql.strip():
        return ""
    try:
        stmts = sqlglot.parse(sql, dialect="tsql")
        canonical = ";\n".join(
            stmt.sql(dialect="tsql", normalize=True) for stmt in stmts if stmt is not None
        )
        return hashlib.sha256(canonical.casefold().encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(sql.strip().casefold().encode("utf-8")).hexdigest()


class SelfCorrectionService:
    """Orchestrates deterministic-first, LLM-assisted SQL self-correction.

    Validates candidate SQL through a strict order:
        1. SQLSyntaxValidator (Deterministic AST / Read-only parser)
        2. SQLSchemaValidator (Deterministic Physical Schema verification)
        3. SQLRelationshipValidator (Deterministic Semantic Relationship verification)
        4. SQLRlsValidator (Deterministic Parameterized RLS mapping & equivalence)
        5. SQLDeterministicRepairService (Deterministic AST Repair)
        6. SQLCriticService (LLM critic - advisory only)
        7. CriticFindingVerifier (Deterministic evidence grounding check)
        8. SQLCorrectionService (LLM correction for validated issues only)

    Tracks candidate fingerprints and halts immediately upon detecting oscillation.
    """

    def __init__(
        self,
        context_retrieval_service: ContextRetrievalService,
        syntax_validator: SQLSyntaxValidator,
        schema_validator: SQLSchemaValidator,
        relationship_validator: SQLRelationshipValidator,
        critic_service: SQLCriticService,
        finding_verifier: CriticFindingVerifier,
        correction_service: SQLCorrectionService,
        max_attempts: int = 3,
        rls_validator: SQLRlsValidator | None = None,
        schema_provider: PhysicalSchemaRepository | None = None,
        repair_service: SQLDeterministicRepairService | None = None,
    ) -> None:
        self._context_retrieval_service = context_retrieval_service
        self._syntax_validator = syntax_validator
        self._schema_validator = schema_validator
        self._relationship_validator = relationship_validator
        self._critic_service = critic_service
        self._finding_verifier = finding_verifier
        self._correction_service = correction_service
        self._max_attempts = max_attempts
        self._rls_validator = rls_validator
        self._schema_provider = schema_provider or getattr(
            schema_validator, "_schema_provider", None
        )
        self._repair_service = repair_service or SQLDeterministicRepairService(
            syntax_validator=syntax_validator,
            schema_validator=schema_validator,
            rls_validator=rls_validator,
            relationship_validator=relationship_validator,
        )

    def run(
        self,
        question: str,
        sql: str,
        semantic_context: str | None = None,
        trace_observer: TraceObserver | None = None,
        enforce_rls: bool = False,
    ) -> SelfCorrectionOutcome:
        """Validate candidate SQL and run bounded correction loops if defects exist."""
        semantic_context = semantic_context or self._context_retrieval_service.build_llm_context(question)
        current_sql = sql
        last_issues: list[ValidationIssue] = []
        trace: list[dict[str, object]] = []
        corrections_used = 0
        cached_schema: dict[str, Any] | None = None
        seen_fingerprints: list[str] = []
        rejected_candidates: list[tuple[str, list[ValidationIssue]]] = []

        def _get_schema() -> dict[str, Any]:
            nonlocal cached_schema
            if cached_schema is None:
                if self._schema_provider is not None:
                    cached_schema = self._schema_provider.get_schema()
                elif hasattr(self._schema_validator, "_schema_provider") and self._schema_validator._schema_provider is not None:
                    cached_schema = self._schema_validator._schema_provider.get_schema()
                else:
                    cached_schema = {}
            return cached_schema

        # Pre-pass: Deterministic projection ambiguity qualification
        qualifier = getattr(
            self._schema_validator, "qualify_base_table_projection_ambiguities", None
        )
        if callable(qualifier) and self._syntax_validator.validate(current_sql).is_valid:
            current_sql = qualifier(current_sql, schema=_get_schema())

        # Pre-pass: Deterministic repair if safe before calling LLM
        initial_issues = self._deterministic_issues(current_sql, _get_schema, enforce_rls=enforce_rls)
        if initial_issues:
            with stage("self_correction", operation="deterministic_repair", is_leaf=False):
                t_rep_start = time.perf_counter()
                repaired_sql = self._repair_service.repair(current_sql, schema=_get_schema(), enforce_rls=enforce_rls)
                rep_dur_ms = (time.perf_counter() - t_rep_start) * 1000
                if repaired_sql != current_sql:
                    post_rep_issues = self._deterministic_issues(repaired_sql, _get_schema, enforce_rls=enforce_rls)
                    if not post_rep_issues:
                        logger.info("Deterministic repair resolved initial issues without LLM correction")
                        current_sql = repaired_sql

        for attempt in range(self._max_attempts + 1):
            logger.info("Self-correction attempt %s", attempt)

            current_fp = compute_sql_fingerprint(current_sql)
            previous_fp = seen_fingerprints[-1] if seen_fingerprints else None

            # Oscillation & Repeat Detection
            if current_fp in seen_fingerprints:
                logger.warning("Correction oscillation detected for fingerprint %s. Aborting loop.", current_fp[:12])
                last_issues = [
                    ValidationIssue(
                        "CORRECTION_OSCILLATION",
                        "CORRECTION_OSCILLATION: Query oscillated or repeated a previously evaluated semantic state.",
                        "self_correction",
                    )
                ]
                trace.append({
                    "attempt": attempt,
                    "sql": current_sql,
                    "sqlFingerprint": current_fp,
                    "previousFingerprint": previous_fp,
                    "deterministicIssues": [issue.message for issue in last_issues],
                    "action": "oscillation_detected",
                })
                self._notify_trace_observer(trace_observer, trace[-1])
                break

            seen_fingerprints.append(current_fp)

            t_det_start = time.perf_counter()
            issues = self._deterministic_issues(current_sql, _get_schema, enforce_rls=enforce_rls)
            det_dur_ms = (time.perf_counter() - t_det_start) * 1000

            # If deterministic issues exist, try deterministic repair on this iteration
            repair_applied = False
            if issues:
                with stage("self_correction", operation="deterministic_repair", is_leaf=False):
                    t_rep = time.perf_counter()
                    repaired = self._repair_service.repair(current_sql, schema=_get_schema(), enforce_rls=enforce_rls)
                    rep_dur = (time.perf_counter() - t_rep) * 1000
                    if repaired != current_sql:
                        rep_issues = self._deterministic_issues(repaired, _get_schema, enforce_rls=enforce_rls)
                        if not rep_issues:
                            current_sql = repaired
                            issues = []
                            repair_applied = True

            trace.append({
                "attempt": attempt,
                "sql": current_sql,
                "deterministicIssues": [issue.message for issue in issues],
                "deterministicDurationMs": det_dur_ms,
            })

            if not issues:
                with stage("self_correction", operation="critic", is_leaf=False):
                    t_critic_start = time.perf_counter()
                    with stage("self_correction", operation="critic_context", is_leaf=True):
                        critic_context = self._build_critic_context(
                            sql=current_sql,
                            schema_getter=_get_schema,
                            fallback_context=semantic_context,
                        )
                    with stage("self_correction", operation="critic_evaluation", is_leaf=True):
                        critic_result = self._critic_service.evaluate(
                            question=question,
                            sql=current_sql,
                            semantic_context=critic_context,
                        )
                    with stage("self_correction", operation="critic_verifier", is_leaf=True):
                        t_ver_start = time.perf_counter()
                        try:
                            issues = self._finding_verifier.verify(critic_result, schema=_get_schema(), sql=current_sql)
                        except TypeError:
                            try:
                                issues = self._finding_verifier.verify(critic_result, schema=_get_schema())
                            except TypeError:
                                issues = self._finding_verifier.verify(critic_result)
                        ver_dur_ms = (time.perf_counter() - t_ver_start) * 1000
                    critic_dur_ms = (time.perf_counter() - t_critic_start) * 1000
                    trace[-1]["criticStatus"] = critic_result.status
                    trace[-1]["criticDurationMs"] = critic_dur_ms
                    trace[-1]["verifiedCriticIssues"] = [issue.message for issue in issues]

                    try:
                        from src.observability.latency_audit import record_critic
                        record_critic(
                            status=critic_result.status,
                            findings_count=len(critic_result.issues),
                            finding_categories=[getattr(iss, "type", str(iss)) for iss in critic_result.issues],
                            total_duration_ms=critic_dur_ms,
                            llm_duration_ms=max(0.0, critic_dur_ms - ver_dur_ms),
                            verifier_duration_ms=ver_dur_ms,
                        )
                    except Exception:
                        pass

            if not issues:
                logger.info("Validation passed on attempt %s", attempt)
                self._notify_trace_observer(
                    trace_observer, {**trace[-1], "action": "passed"}
                )
                return SelfCorrectionOutcome.success(
                    current_sql, attempts_used=attempt, trace=tuple(trace)
                )

            last_issues = issues

            for issue in issues:
                logger.info("Validation issue [%s]: %s", issue.type, issue.message)

            if attempt == self._max_attempts:
                logger.info("Self-correction stopped: maximum attempts (%s) reached", self._max_attempts)
                self._notify_trace_observer(
                    trace_observer,
                    {**trace[-1], "action": "maximum_attempts_reached"},
                )
                break

            self._notify_trace_observer(
                trace_observer,
                {**trace[-1], "action": "correction_required"},
            )

            try:
                corrections_used += 1
                with stage("self_correction", operation=f"correction_attempt_{attempt + 1}", is_leaf=False):
                    t_corr_start = time.perf_counter()
                    with stage("self_correction", operation="correction_prep", is_leaf=True):
                        rls_tables = self._rls_context_tables(
                            current_sql, _get_schema
                        )
                        try:
                            tables_in_sql = self._schema_validator.extract_tables(
                                current_sql, schema=_get_schema()
                            )
                        except Exception:
                            tables_in_sql = set()
                        bridging_tables = self._bridging_tables(
                            tables_in_sql, schema=_get_schema()
                        )
                        extra_context_tables = rls_tables | bridging_tables

                        cand_fp = compute_sql_fingerprint(current_sql)
                        if not any(compute_sql_fingerprint(cand[0]) == cand_fp for cand in rejected_candidates):
                            rejected_candidates.append((current_sql, list(issues)))

                    with stage("self_correction", operation="correction_llm", is_leaf=True):
                        corrected_sql = self._correction_service.correct(
                            question=question,
                            current_sql=current_sql,
                            issues=issues,
                            relevant_schema=self._relevant_schema(
                                current_sql, _get_schema, extra_tables=extra_context_tables
                            ),
                            relevant_relationships=self._relevant_relationships(
                                current_sql, _get_schema, extra_tables=extra_context_tables
                            ),
                            rejected_candidates=list(rejected_candidates),
                        )
                    corr_dur_ms = (time.perf_counter() - t_corr_start) * 1000
                    trace[-1]["correctionDurationMs"] = corr_dur_ms

                    try:
                        from src.observability.latency_audit import record_correction_attempt
                        record_correction_attempt(
                            attempt=attempt + 1,
                            trigger_reason="; ".join(issue.message for issue in issues)[:120],
                            duration_ms=corr_dur_ms,
                            previous_sql=current_sql,
                            new_sql=corrected_sql,
                            issues_count=len(issues),
                        )
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("SQL correction call failed: %s", type(exc).__name__)
                trace[-1]["correctionError"] = type(exc).__name__
                self._notify_trace_observer(
                    trace_observer,
                    {
                        "event": "correction_failed",
                        "attempt": attempt + 1,
                        "error": type(exc).__name__,
                    },
                )
                break

            if not corrected_sql:
                logger.info("Self-correction stopped: correction model returned no SQL")
                self._notify_trace_observer(
                    trace_observer,
                    {"event": "correction_returned_no_sql", "attempt": attempt + 1},
                )
                break

            logger.info("SQL correction generated for attempt %s", attempt + 1)
            trace[-1]["correctedSql"] = corrected_sql
            self._notify_trace_observer(
                trace_observer,
                {
                    "event": "after_correction",
                    "attempt": attempt + 1,
                    "previousSql": current_sql,
                    "sql": corrected_sql,
                    "changed": corrected_sql != current_sql,
                },
            )
            current_sql = corrected_sql

        return SelfCorrectionOutcome.failure(
            attempts_used=corrections_used,
            issues=tuple(issue.message for issue in last_issues),
            trace=tuple(trace),
        )

    @staticmethod
    def _notify_trace_observer(
        trace_observer: TraceObserver | None,
        step: dict[str, Any],
    ) -> None:
        """Publish optional diagnostic data without affecting correction behavior."""
        if trace_observer is None:
            return
        try:
            trace_observer(dict(step))
        except Exception:
            logger.warning("Self-correction trace observer failed", exc_info=True)

    def _deterministic_issues(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]] | None = None,
        enforce_rls: bool = False,
    ) -> list[ValidationIssue]:
        t0 = time.perf_counter()
        schema = schema_getter() if schema_getter is not None else None
        sub_stages: dict[str, float] = {}
        validators = [
            ("syntax", self._syntax_validator),
            ("schema", self._schema_validator),
            ("relationship", self._relationship_validator),
        ]
        if self._rls_validator is not None:
            validators.append(("rls", self._rls_validator))

        found_issues: list[ValidationIssue] = []
        with stage("self_correction", operation="deterministic_validation", is_leaf=False):
            for name, validator in validators:
                with stage("self_correction", operation=f"deterministic_validation_{name}", is_leaf=True):
                    t_sub = time.perf_counter()
                    try:
                        if validator is self._rls_validator:
                            result = validator.validate(sql, schema=schema, enforce_presence=enforce_rls)
                        else:
                            result = validator.validate(sql, schema=schema)
                    except TypeError:
                        result = validator.validate(sql)
                    sub_stages[f"{name}_ms"] = round((time.perf_counter() - t_sub) * 1000.0, 2)
                    if not result.is_valid:
                        found_issues = list(result.issues)
                        break

        tot_ms = (time.perf_counter() - t0) * 1000.0
        try:
            from src.observability.latency_audit import record_validation
            from src.observability.audit_context import get_current_audit

            ctx = get_current_audit()
            if ctx:
                ctx.record_leaf_duration("deterministic_validation", tot_ms)
            record_validation(
                stage_name="deterministic_validation",
                sql=sql,
                is_valid=len(found_issues) == 0,
                findings=found_issues,
                duration_ms=tot_ms,
                sub_stages=sub_stages,
            )
        except Exception:
            pass

        return found_issues

    def _relevant_schema(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]] | None = None,
        extra_tables: set[str] | None = None,
    ) -> dict:
        schema = schema_getter() if schema_getter is not None else None
        try:
            result = self._schema_validator.schema_slice(sql, schema=schema)
            all_tables = (schema or {}).get("tables", {})
            if isinstance(all_tables, dict):
                result.update(
                    {
                        table: all_tables[table]
                        for table in extra_tables or set()
                        if table in all_tables
                    }
                )
            return result
        except TypeError:
            try:
                return self._schema_validator.schema_slice(sql)
            except Exception:
                return {}
        except Exception:
            return {}

    def _relevant_relationships(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]] | None = None,
        extra_tables: set[str] | None = None,
    ) -> list[dict]:
        schema = schema_getter() if schema_getter is not None else None
        try:
            tables = self._schema_validator.extract_tables(sql, schema=schema)
        except TypeError:
            try:
                tables = self._schema_validator.extract_tables(sql)
            except Exception:
                return []
        except Exception:
            return []
        if self._relationship_validator is None:
            return []
        return self._relationship_validator.relationships_for_tables(
            tables | (extra_tables or set())
        )

    def _rls_context_tables(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]] | None = None,
    ) -> set[str]:
        """Add intermediate tables required by active security domains to repair SQL."""
        schema = schema_getter() if schema_getter is not None else None
        try:
            tables = self._schema_validator.extract_tables(sql, schema=schema)
        except Exception:
            return set()

        security_domains = []
        if self._rls_validator is not None:
            loader = getattr(self._rls_validator, "_load_security_domains", None)
            if callable(loader):
                security_domains = loader(schema=schema)

        if not security_domains and isinstance(schema, dict):
            security_domains = schema.get("security_domains", [])

        if not security_domains and self._relationship_validator is not None:
            repo = getattr(self._relationship_validator, "_semantic_repository", None)
            if repo is not None:
                try:
                    layer = repo.load()
                    if isinstance(layer, dict):
                        security_domains = layer.get("security_domains", [])
                except Exception:
                    pass

        if not security_domains:
            return set()

        needed_tables: set[str] = set()
        for domain in security_domains:
            if not isinstance(domain, dict):
                continue
            canonical_root = domain.get("canonical_root", "")
            root_table = canonical_root.split(".", 1)[0] if "." in canonical_root else canonical_root
            propagation_paths = domain.get("propagation_paths", [])
            for path_entry in propagation_paths:
                if not isinstance(path_entry, dict):
                    continue
                target = path_entry.get("target_table")
                if target in tables:
                    if root_table:
                        needed_tables.add(root_table)
                    path_str = path_entry.get("path", "")
                    for token in path_str.replace("->", " ").replace("=", " ").split():
                        if "." in token:
                            tbl = token.split(".", 1)[0].strip()
                            if tbl:
                                needed_tables.add(tbl)
        return needed_tables - tables

    def _bridging_tables(
        self,
        tables: set[str],
        schema: dict[str, Any] | None = None,
    ) -> set[str]:
        """Find intermediate 1-hop bridging tables connecting tables in the query."""
        if not tables or len(tables) < 2:
            return set()
        relationships = []
        if self._relationship_validator is not None:
            repo = getattr(self._relationship_validator, "_semantic_repository", None)
            if repo is not None:
                try:
                    relationships = repo.load().get("relationships", [])
                except Exception:
                    pass
        if not relationships and isinstance(schema, dict):
            relationships = schema.get("relationships", [])

        if not isinstance(relationships, list):
            return set()

        adj: dict[str, set[str]] = {}
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            ft, tt = rel.get("from_table"), rel.get("to_table")
            if ft and tt and isinstance(ft, str) and isinstance(tt, str):
                adj.setdefault(ft, set()).add(tt)
                adj.setdefault(tt, set()).add(ft)

        bridging: set[str] = set()
        for t1 in tables:
            for t2 in tables:
                if t1 == t2:
                    continue
                if t2 not in adj.get(t1, set()):
                    common = (adj.get(t1, set()) & adj.get(t2, set())) - tables
                    bridging.update(common)

        return bridging

    def _build_critic_context(
        self,
        sql: str,
        schema_getter: Callable[[], dict[str, Any]],
        fallback_context: str,
    ) -> str:
        """Build a compact, table-relevant semantic slice for the Critic to minimize token latency."""
        try:
            rel_schema = self._relevant_schema(sql, schema_getter)
            if not rel_schema:
                return fallback_context

            lines = ["RELEVANT TABLES & SCHEMA:"]
            for table_name, table_info in sorted(rel_schema.items()):
                cols = [
                    c["name"]
                    for c in table_info.get("columns", [])
                    if isinstance(c, dict) and "name" in c
                ]
                lines.append(f"TABLE: {table_name}")
                lines.append(f"COLUMNS: {', '.join(cols)}")

            rel_relationships = self._relevant_relationships(sql, schema_getter)
            if rel_relationships:
                lines.append("\nRELEVANT RELATIONSHIPS:")
                for r in rel_relationships:
                    lines.append(
                        f"- {r.get('from_table')}.{r.get('from_column')} -> {r.get('to_table')}.{r.get('to_column')}"
                    )

            domains = []
            if self._context_retrieval_service is not None:
                repo = getattr(self._context_retrieval_service, "_semantic_repository", None)
                if repo is not None:
                    try:
                        layer = repo.load()
                        if isinstance(layer, dict):
                            domains = layer.get("security_domains", [])
                    except Exception:
                        pass
            if not domains and self._rls_validator is not None:
                loader = getattr(self._rls_validator, "_load_security_domains", None)
                if callable(loader):
                    try:
                        domains = loader(schema=schema_getter())
                    except Exception:
                        pass
            if not domains:
                schema = schema_getter()
                domains = schema.get("security_domains", []) if isinstance(schema, dict) else []

            if domains:
                lines.append("\nSECURITY POLICY:")
                for d in domains:
                    if not isinstance(d, dict):
                        continue
                    name = d.get("name", "domain")
                    pred = d.get("canonical_predicate") or d.get("canonical_root")
                    scope = d.get("security_scope")
                    parts = [f"{name}: {pred}"]
                    if scope:
                        parts.append(f"scope: {scope}")
                    lines.append(f"- {', '.join(parts)}")
                    props = d.get("propagation_paths", [])
                    if isinstance(props, list) and props:
                        for p in props:
                            if isinstance(p, dict):
                                target = p.get("target_table")
                                path = p.get("path")
                                if target and path:
                                    lines.append(f"  * propagation to {target}: {path}")

            return "\n".join(lines)
        except Exception:
            return fallback_context

