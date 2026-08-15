"""In-process stand-in for the Backend, wired to the real application code.

This class exists ONLY so Module 2 of the API spec can be exercised
end-to-end without a running Backend or a running LLM. Every method
here corresponds 1:1 to an endpoint in the spec and:

  1. Accepts the exact camelCase JSON shape the spec's REQUEST shows.
  2. Delegates to the *real* pipelines/services under src/application.
  3. Returns the exact camelCase JSON shape the spec's RESPONSE shows.

Two deviations from the literal doc text are called out inline with
`# SPEC GAP:` comments -- see the summary printed at the end of
run_integration_scenarios.py for the full list.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from ai.tests.integration.semantic_layer_test_scripts.case_convert import to_camel, to_snake

from src.application.dto.backend.semantic_layer.semantic_layer_generation_request import (
    AffectedObject,
    SemanticLayerGenerationRequest,
)
from src.application.pipelines.semantic_layer.semantic_layer_generation_pipeline import (
    SemanticLayerGenerationPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_review_pipeline import (
    SemanticLayerReviewPipeline,
)
from src.application.pipelines.semantic_layer.semantic_layer_validation_pipeline import (
    SemanticLayerValidationPipeline,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)
from src.application.services.semantic_layer.builders.incremental_builder import (
    IncrementalBuilder,
)
from src.application.services.semantic_layer.merge.semantic_layer_merger_service import (
    SemanticLayerMergeService,
)
from src.application.services.semantic_layer.review_manager import (
    HumanReviewManager,
)
from src.application.services.semantic_layer.semantic_layer_build_service import (
    SemanticLayerBuildService,
)
from src.application.services.semantic_layer.semantic_layer_identity_service import (
    SemanticLayerIdentityService,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)
from src.application.services.semantic_layer.strategy.full_rebuild_strategy import (
    FullRebuildStrategy,
)
from src.application.services.semantic_layer.strategy.incremental_build_strategy import (
    IncrementalBuildStrategy,
)
from src.application.services.semantic_layer.validation.semantic_layer_auto_fixer import (
    SemanticLayerAutoFixer,
)
from src.application.services.semantic_layer.validation.semantic_layer_validator import (
    SemanticLayerValidator,
)
from src.infrastructure.semantic_layer.persistence.semantic_layer_id_generator import (
    SemanticLayerIdGenerator,
)

_CONTENT_SECTIONS = (
    "entities",
    "relationships",
    "measures",
    "dimensions",
    "business_rules",
    "validation_issues",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockSemanticLayerBackend:
    """Everything a real Backend controller would do for Module 2,
    minus HTTP and a database -- state lives in memory."""

    def __init__(self, llm_client, schema: dict[str, Any]) -> None:
        id_generator = SemanticLayerIdGenerator()

        build_service = SemanticLayerBuildService(
            full_rebuild_strategy=FullRebuildStrategy(
                FullRebuildBuilder(llm_client)
            ),
            incremental_strategy=IncrementalBuildStrategy(
                IncrementalBuilder(llm_client)
            ),
        )

        self._generation_pipeline = SemanticLayerGenerationPipeline(
            build_service=build_service,
            merge_service=SemanticLayerMergeService(),
            metadata_service=SemanticLayerMetadataService(id_generator),
            identity_service=SemanticLayerIdentityService(),
        )

        self._validation_pipeline = SemanticLayerValidationPipeline(
            validator=SemanticLayerValidator(),
            auto_fixer=SemanticLayerAutoFixer(llm_client),
            max_fix_attempts=2,
        )

        self._review_pipeline = SemanticLayerReviewPipeline(
            HumanReviewManager()
        )

        self._schema = schema

        # In-memory "database"
        self._sources: dict[str, dict[str, Any]] = {}
        self._layers: dict[str, dict[str, Any]] = {}
        # (semanticLayerId, revisionId) -> {"draft": ..., "validation": ...}
        self._revisions: dict[tuple[str, str], dict[str, Any]] = {}
        # semanticLayerId -> currently approved draft (base for Incremental)
        self._approved: dict[str, dict[str, Any]] = {}
        # semanticLayerId -> integer version counter of approved revisions
        self._version_counter: dict[str, int] = {}

    # ------------------------------------------------------------------
    # 2.1 Upload Data Sources
    # ------------------------------------------------------------------
    def upload_sources(self, request: dict[str, Any]) -> dict[str, Any]:
        semantic_layer_id = f"sl-{uuid.uuid4().hex[:8]}"

        source_map = request.get("sources", {})
        file_ids: dict[str, str] = {}
        stored_sources: dict[str, Any] = {}

        for source_kind, payload in source_map.items():
            file_id = f"file-{uuid.uuid4().hex[:8]}"
            file_ids[source_kind] = file_id
            self._sources[file_id] = {
                "fileId": file_id,
                "fileType": source_kind,
                "fileName": payload.get("fileName"),
                "content": payload.get("content"),
            }
            stored_sources[source_kind] = file_id

        self._layers[semantic_layer_id] = {
            "name": request.get("name"),
            "description": request.get("description"),
        }

        return {
            "status": "SourcesLoaded",
            "message": "Sources loaded successfully.",
            "semanticLayerId": semantic_layer_id,
            "name": request.get("name"),
            "description": request.get("description"),
            "sources": {
                "schemaFileId": file_ids.get("schema"),
                "documentationFileId": file_ids.get("documentation"),
                "glossaryFileId": file_ids.get("glossary"),
                "sampleDataFileId": file_ids.get("sampleData"),
            },
            "hasDocumentation": "documentation" in file_ids,
            "hasGlossary": "glossary" in file_ids,
            "hasSampleData": "sampleData" in file_ids,
        }

    # ------------------------------------------------------------------
    # 2.2 Retrieve Semantic Layer Source File
    # ------------------------------------------------------------------
    def get_file(self, file_id: str) -> dict[str, Any]:
        record = self._sources[file_id]

        return {
            "status": "Success",
            "fileId": record["fileId"],
            "fileType": record["fileType"],
            "fileName": record["fileName"],
            "content": record["content"],
        }

    # ------------------------------------------------------------------
    # 2.3 Trigger Semantic Metadata Generation
    # ------------------------------------------------------------------
    def generate_draft(self, request: dict[str, Any]) -> dict[str, Any]:
        semantic_layer_id = request.get("semanticLayerId")
        trigger_type = request["triggerType"]
        source_file_ids = tuple(request["sourceFileIds"])

        affected_objects = tuple(
            AffectedObject(
                object_id=obj["objectId"],
                section=obj["section"],
                name=obj["name"],
                action=obj["action"],
            )
            for obj in request.get("affectedObjects", [])
        )

        gen_request = SemanticLayerGenerationRequest(
            trigger_type=trigger_type,
            source_file_ids=source_file_ids,
            semantic_layer_id=(
                semantic_layer_id if trigger_type == "Incremental" else None
            ),
            base_revision_id=(
                request.get("baseRevisionId")
                if trigger_type == "Incremental"
                else None
            ),
            affected_objects=affected_objects,
        )

        sources = self._resolve_sources(source_file_ids)

        base_semantic_layer = None
        if trigger_type == "Incremental":
            base_semantic_layer = self._approved[semantic_layer_id]

        draft = self._generation_pipeline.run(
            request=gen_request,
            sources=sources,
            base_semantic_layer=base_semantic_layer,
        )

        final_draft, validation = self._validation_pipeline.run(
            draft=draft,
            schema=self._schema,
        )

        final_semantic_layer_id = final_draft["metadata"]["semantic_layer_id"]
        revision_id = final_draft["metadata"]["revision_id"]

        final_draft["metadata"]["status"] = (
            "pending_review" if validation["status"] == "passed"
            else "validation_failed"
        )

        self._revisions[(final_semantic_layer_id, revision_id)] = {
            "draft": final_draft,
            "validation": validation,
            "build_timestamp": _now(),
            "trigger_type": trigger_type,
            "created_at": _now(),
        }

        if trigger_type == "Incremental":
            regenerated_count = len(affected_objects)
        else:
            regenerated_count = sum(
                len(final_draft.get(section, []))
                for section in _CONTENT_SECTIONS
                if section != "validation_issues"
            )

        return {
            "status": "DraftGenerated",
            "semanticLayerId": final_semantic_layer_id,
            "revisionId": revision_id,
            "baseRevisionId": request.get("baseRevisionId"),
            "regeneratedObjectsCount": regenerated_count,
            "buildTimestamp": self._revisions[
                (final_semantic_layer_id, revision_id)
            ]["build_timestamp"],
            "lastRegenerationType": trigger_type,
        }

    # ------------------------------------------------------------------
    # 2.4 Retrieve Semantic Revision
    # ------------------------------------------------------------------
    def get_revision(
        self, semantic_layer_id: str, revision_id: str
    ) -> dict[str, Any]:
        record = self._revisions[(semantic_layer_id, revision_id)]
        draft = record["draft"]
        metadata = draft["metadata"]

        status_map = {
            "pending_review": "PendingReview",
            "validation_failed": "ValidationFailed",
            "approved": "Approved",
            "rejected": "Rejected",
        }

        content = {
            section: draft.get(section, [])
            for section in _CONTENT_SECTIONS
        }

        return {
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "status": status_map.get(metadata["status"], metadata["status"]),
            "version": (
                f"v{metadata.get('version')}"
                if metadata.get("version") is not None
                else "draft"
            ),
            "buildTimestamp": record["build_timestamp"],
            "lastRegenerationType": record["trigger_type"],
            "content": to_camel(content),
            "createdAt": record["created_at"],
        }

    # ------------------------------------------------------------------
    # 2.5 Human Review & Approval
    # ------------------------------------------------------------------
    def review(self, request: dict[str, Any]) -> dict[str, Any]:
        semantic_layer_id = request["semanticLayerId"]
        revision_id = request["revisionId"]
        decision = request["decision"]
        comments = request.get("comments", "")

        record = self._revisions[(semantic_layer_id, revision_id)]

        reviewed_draft, review_result = self._review_pipeline.run(
            draft=record["draft"],
            validation=record["validation"],
            decision="approve" if decision == "Approve" else "reject",
            reviewer="usr-123",
            comments=comments,
        )

        record["draft"] = reviewed_draft

        if decision == "Approve":
            self._version_counter[semantic_layer_id] = (
                self._version_counter.get(semantic_layer_id, 0) + 1
            )
            version = f"v1.{self._version_counter[semantic_layer_id] - 1}"
            reviewed_draft["metadata"]["version"] = version.lstrip("v")

            self._approved[semantic_layer_id] = deepcopy(reviewed_draft)

            return {
                "semanticLayerId": semantic_layer_id,
                "revisionId": revision_id,
                "status": "Approved",
                "version": version,
                "approvedBy": review_result["reviewer"],
                "approvedAt": review_result["reviewed_at"],
            }

        return {
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "status": "Rejected",
            "comments": review_result["comments"],
            "rejectedBy": review_result["reviewer"],
            "rejectedAt": review_result["reviewed_at"],
        }

    # ------------------------------------------------------------------
    # 2.6 Update & Submit Revision
    # ------------------------------------------------------------------
    def update_revision(
        self,
        semantic_layer_id: str,
        revision_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        record = self._revisions[(semantic_layer_id, revision_id)]
        draft = record["draft"]

        # SPEC GAP: the doc's 2.6 example content uses the key "tables"
        # where every other module uses "entities" for this section.
        # Treated as a documentation typo and mapped to "entities" here.
        edited = to_snake(request.get("content", {}))
        if "tables" in edited:
            edited["entities"] = edited.pop("tables")

        for section in _CONTENT_SECTIONS:
            if section in edited:
                draft[section] = edited[section]

        final_draft, validation = self._validation_pipeline.run(
            draft=draft,
            schema=self._schema,
        )

        final_draft["metadata"]["status"] = (
            "pending_review" if validation["status"] == "passed"
            else "validation_failed"
        )

        record["draft"] = final_draft
        record["validation"] = validation

        return {
            "status": "Submitted",
            "semanticLayerId": semantic_layer_id,
            "revisionId": revision_id,
            "message": "Revision updated and submitted for validation.",
        }

    # ------------------------------------------------------------------
    # 2.7 Semantic Layer Status
    # ------------------------------------------------------------------
    def get_status(self, semantic_layer_id: str) -> dict[str, Any]:
        matching = [
            (rev_id, rec)
            for (sl_id, rev_id), rec in self._revisions.items()
            if sl_id == semantic_layer_id
        ]
        revision_id, record = max(
            matching, key=lambda pair: pair[1]["created_at"]
        )
        metadata = record["draft"]["metadata"]

        status_map = {
            "pending_review": "PendingReview",
            "validation_failed": "ValidationFailed",
            "approved": "Approved",
            "rejected": "Rejected",
        }

        return {
            "semanticLayerId": semantic_layer_id,
            "status": status_map.get(metadata["status"], metadata["status"]),
            "version": (
                f"v{metadata['version']}"
                if metadata.get("version") is not None
                else "draft"
            ),
            "revisionId": revision_id,
            "buildTimestamp": record["build_timestamp"],
            "lastRegenerationType": record["trigger_type"],
        }

    # ------------------------------------------------------------------
    def _resolve_sources(
        self, source_file_ids: tuple[str, ...]
    ) -> dict[str, Any]:
        sources: dict[str, Any] = {}

        for file_id in source_file_ids:
            record = self._sources[file_id]
            kind = record["fileType"]

            if kind == "schema":
                sources["schema"] = self._schema["tables"]
                sources["relationships"] = self._schema["relationships"]
            elif kind == "documentation":
                sources["documentation"] = record["content"]
            elif kind == "glossary":
                sources["business_glossary"] = record["content"]
            elif kind == "sampleData":
                sources["sample_data"] = record["content"]

        return sources
