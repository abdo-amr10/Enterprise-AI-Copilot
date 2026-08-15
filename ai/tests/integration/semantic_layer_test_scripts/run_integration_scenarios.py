"""Runs the semantic_layer code end-to-end against Module 2 of the API
spec, without a live Backend or a live LLM.

Usage:
    python3 run_integration_scenarios.py            # print to stdout
    python3 run_integration_scenarios.py > out.json  # capture transcript
"""

import json
import sys

sys.path.insert(0, "..")  # project root, so `import src....` resolves

from ai.tests.integration.semantic_layer_test_scripts.fake_llm_client import FakeLLMClient
from ai.tests.integration.semantic_layer_test_scripts.mock_backend import MockSemanticLayerBackend
import ai.tests.integration.semantic_layer_test_scripts.fixtures as fx

TRANSCRIPT: list[dict] = []


def call(step: str, method: str, path: str, request_body, fn, *args, **kwargs):
    """Invoke one backend method, recording it exactly like an HTTP call."""

    response_body = fn(*args, **kwargs)

    TRANSCRIPT.append(
        {
            "step": step,
            "method": method,
            "path": path,
            "request": request_body,
            "response": response_body,
        }
    )

    return response_body


def main() -> None:
    backend = MockSemanticLayerBackend(
        llm_client=(llm := FakeLLMClient([])),
        schema=fx.SCHEMA,
    )

    # ---------------------------------------------------------------
    # 2.1 Upload Data Sources
    # ---------------------------------------------------------------
    upload_req = {
        "name": "ERP Semantic Layer",
        "description": "Semantic layer for ERP database",
        "sources": {
            "schema": {"fileName": "schema.json", "content": fx.SCHEMA},
            "documentation": {
                "fileName": "documentation.md",
                "content": fx.DOCUMENTATION,
            },
            "glossary": {"fileName": "glossary.md", "content": fx.GLOSSARY},
            "sampleData": {
                "fileName": "sample.csv",
                "content": fx.SAMPLE_DATA,
            },
        },
    }
    upload_res = call(
        "2.1 Upload Data Sources",
        "POST",
        "/api/v1/semantic-layer/upload",
        upload_req,
        backend.upload_sources,
        upload_req,
    )

    semantic_layer_id = upload_res["semanticLayerId"]
    source_file_ids = {
        "schema": upload_res["sources"]["schemaFileId"],
        "documentation": upload_res["sources"]["documentationFileId"],
        "glossary": upload_res["sources"]["glossaryFileId"],
        "sampleData": upload_res["sources"]["sampleDataFileId"],
    }

    # ---------------------------------------------------------------
    # 2.2 Retrieve one uploaded source file (schema)
    # ---------------------------------------------------------------
    schema_file_id = upload_res["sources"]["schemaFileId"]
    call(
        "2.2 Retrieve Semantic Layer Source File",
        "GET",
        f"/api/v1/semantic-layer/files/{schema_file_id}",
        None,
        backend.get_file,
        schema_file_id,
    )

    # ---------------------------------------------------------------
    # 2.3 Trigger Semantic Metadata Generation -- FullRebuild (happy path)
    # ---------------------------------------------------------------
    llm.calls.clear()
    llm._queue.append(fx.FULL_REBUILD_DRAFT_TEXT)

    gen_req = {
        "semanticLayerId": None,
        "triggerType": "FullRebuild",
        "sourceFileIds": source_file_ids,
    }
    gen_res = call(
        "2.3 Generate Draft (FullRebuild)",
        "POST",
        "/api/v1/semantic-layer/generate-draft",
        {k: v for k, v in gen_req.items() if v is not None},
        backend.generate_draft,
        gen_req,
    )

    revision_id = gen_res["revisionId"]

    # NOTE / SPEC GAP: SemanticLayerMetadataService.initialize() mints a
    # brand-new semantic_layer_id for every FullRebuild, regardless of
    # what was assigned at upload time (2.1). The spec's examples all
    # reuse "sl-001" across 2.1 -> 2.7 as if it were the same ID
    # throughout, but the current code never reuses the upload-time ID
    # for a FullRebuild draft -- the ID returned by 2.3 is the one that
    # must be used from here on, not the one from 2.1. Using it below.
    semantic_layer_id = gen_res["semanticLayerId"]

    # ---------------------------------------------------------------
    # 2.4 Retrieve Semantic Revision, for Admin review
    # ---------------------------------------------------------------
    call(
        "2.4 Retrieve Semantic Revision",
        "GET",
        f"/api/v1/semantic-layer/{semantic_layer_id}/revisions/{revision_id}",
        None,
        backend.get_revision,
        semantic_layer_id,
        revision_id,
    )

    # ---------------------------------------------------------------
    # 2.5 Human Review & Approval -- Approve
    # ---------------------------------------------------------------
    approve_req = {
        "semanticLayerId": semantic_layer_id,
        "revisionId": revision_id,
        "decision": "Approve",
    }
    call(
        "2.5 Human Review & Approval (Approve)",
        "POST",
        "/api/v1/semantic-layer/review",
        approve_req,
        backend.review,
        approve_req,
    )

    # ---------------------------------------------------------------
    # 2.7 Semantic Layer Status, right after approval
    # ---------------------------------------------------------------
    call(
        "2.7 Semantic Layer Status (after approval)",
        "GET",
        f"/api/v1/semantic-layer/{semantic_layer_id}/status",
        None,
        backend.get_status,
        semantic_layer_id,
    )

    # ---------------------------------------------------------------
    # 2.3 Trigger Semantic Metadata Generation -- Incremental
    # ---------------------------------------------------------------
    llm._queue.append(fx.INCREMENTAL_DRAFT_TEXT)

    incr_req = {
        "semanticLayerId": semantic_layer_id,
        "triggerType": "Incremental",
        "sourceFileIds": {
            key: source_file_ids[key]
            for key in ("schema", "documentation", "glossary")
        },
        "baseRevisionId": revision_id,
        "affectedObjects": [
            {
                "objectId": "obj-temp-001",
                "section": "measures",
                "name": "AverageOrderValue",
                "action": "upsert",
            },
            {
                "objectId": "obj-temp-002",
                "section": "business_rules",
                "name": "ActiveCustomers",
                "action": "upsert",
            },
        ],
    }
    incr_res = call(
        "2.3 Generate Draft (Incremental)",
        "POST",
        "/api/v1/semantic-layer/generate-draft",
        incr_req,
        backend.generate_draft,
        incr_req,
    )

    incr_revision_id = incr_res["revisionId"]

    call(
        "2.4 Retrieve Semantic Revision (Incremental draft)",
        "GET",
        f"/api/v1/semantic-layer/{semantic_layer_id}/revisions/{incr_revision_id}",
        None,
        backend.get_revision,
        semantic_layer_id,
        incr_revision_id,
    )

    # ---------------------------------------------------------------
    # 2.5 Human Review & Approval -- Reject, then 2.6 Update & Submit
    # ---------------------------------------------------------------
    reject_req = {
        "semanticLayerId": semantic_layer_id,
        "revisionId": incr_revision_id,
        "decision": "Reject",
        "comments": "AverageOrderValue description should mention it excludes refunds.",
    }
    call(
        "2.5 Human Review & Approval (Reject)",
        "POST",
        "/api/v1/semantic-layer/review",
        reject_req,
        backend.review,
        reject_req,
    )

    # NOTE: update_revision replaces a whole section wholesale (it
    # mirrors the spec's 2.6 example, which shows full section arrays,
    # not a partial patch) -- so the resubmitted content below repeats
    # TotalRevenue unchanged alongside the corrected AverageOrderValue,
    # otherwise TotalRevenue would be dropped from the revision.
    update_req = {
        "content": {
            "measures": [
                {
                    "name": "TotalRevenue",
                    "mapping": "Sales.Amount",
                    "aggregation": "sum",
                    "description": "Sum of sale amounts.",
                },
                {
                    "name": "AverageOrderValue",
                    "mapping": "Sales.Amount",
                    "aggregation": "avg",
                    "description": (
                        "Average sale amount per transaction, "
                        "excluding refunds."
                    ),
                },
            ]
        }
    }
    call(
        "2.6 Update & Submit Revision",
        "PUT",
        f"/api/v1/semantic-layer/{semantic_layer_id}/revisions/{incr_revision_id}",
        update_req,
        backend.update_revision,
        semantic_layer_id,
        incr_revision_id,
        update_req,
    )

    reapprove_req = {
        "semanticLayerId": semantic_layer_id,
        "revisionId": incr_revision_id,
        "decision": "Approve",
    }
    call(
        "2.5 Human Review & Approval (Approve after edit)",
        "POST",
        "/api/v1/semantic-layer/review",
        reapprove_req,
        backend.review,
        reapprove_req,
    )

    # ---------------------------------------------------------------
    # Bonus: FullRebuild draft that fails validation, then gets
    # auto-fixed by SemanticLayerAutoFixer before reaching Review.
    # ---------------------------------------------------------------
    llm._queue.append(fx.BROKEN_DRAFT_TEXT)
    llm._queue.append(fx.FIXED_DRAFT_TEXT)

    broken_req = {
        "semanticLayerId": None,
        "triggerType": "FullRebuild",
        "sourceFileIds": source_file_ids,
    }
    broken_res = call(
        "2.3 Generate Draft (FullRebuild, auto-fix demo)",
        "POST",
        "/api/v1/semantic-layer/generate-draft",
        {k: v for k, v in broken_req.items() if v is not None},
        backend.generate_draft,
        broken_req,
    )

    call(
        "2.4 Retrieve Semantic Revision (post auto-fix)",
        "GET",
        f"/api/v1/semantic-layer/{broken_res['semanticLayerId']}/revisions/{broken_res['revisionId']}",
        None,
        backend.get_revision,
        broken_res["semanticLayerId"],
        broken_res["revisionId"],
    )

    print(json.dumps(TRANSCRIPT, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
