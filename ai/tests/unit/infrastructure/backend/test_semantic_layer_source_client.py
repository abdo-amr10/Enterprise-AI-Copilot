"""Unit tests for the SemanticLayerSourceClient response parser."""

from __future__ import annotations

from src.infrastructure.backend.clients.semantic_layer_source_client import (
    SemanticLayerSourceClientImpl,
)


def test_parse_upload_response_with_canonical_backend_sources() -> None:
    response = {
        "status": "SourcesLoaded",
        "message": "Sources loaded successfully.",
        "semanticLayerId": "sl-001",
        "name": "Banking Core",
        "description": "Primary banking semantic layer",
        "sources": {
            "schemaFileId": "file-schema-123",
            "documentationFileId": "file-doc-456",
            "glossaryFileId": "file-gloss-789",
            "sampleDataFileId": "file-sample-012",
        },
        "hasDocumentation": True,
        "hasGlossary": True,
        "hasSampleData": True,
    }

    result = SemanticLayerSourceClientImpl._parse_upload_response(response)

    assert result.status == "SourcesLoaded"
    assert result.semantic_layer_id == "sl-001"
    assert result.name == "Banking Core"
    assert result.description == "Primary banking semantic layer"
    assert result.sources["schema"].file_id == "file-schema-123"
    assert result.sources["schema"].file_type == "schema"
    assert result.sources["documentation"].file_id == "file-doc-456"
    assert result.sources["documentation"].file_type == "documentation"
    assert result.sources["glossary"].file_id == "file-gloss-789"
    assert result.sources["glossary"].file_type == "glossary"
    assert result.sources["sampleData"].file_id == "file-sample-012"
    assert result.sources["sampleData"].file_type == "sampleData"


def test_parse_upload_response_with_optional_missing_sources() -> None:
    response = {
        "status": "SourcesLoaded",
        "message": "Sources loaded successfully.",
        "semanticLayerId": "sl-002",
        "name": "Minimal Layer",
        "description": None,
        "sources": {
            "schemaFileId": "file-schema-999",
            "documentationFileId": None,
            "glossaryFileId": None,
            "sampleDataFileId": None,
        },
        "hasDocumentation": False,
        "hasGlossary": False,
        "hasSampleData": False,
    }

    result = SemanticLayerSourceClientImpl._parse_upload_response(response)

    assert result.status == "SourcesLoaded"
    assert result.semantic_layer_id == "sl-002"
    assert result.sources["schema"].file_id == "file-schema-999"
    assert result.sources["documentation"] is None
    assert result.sources["glossary"] is None
    assert result.sources["sampleData"] is None


def test_parse_upload_response_with_legacy_nested_dict() -> None:
    response = {
        "status": "SourcesLoaded",
        "semanticLayerId": "sl-003",
        "name": "Legacy",
        "sources": {
            "schema": {"fileId": "file-old-1", "fileType": "schema"},
            "documentation": None,
        },
    }

    result = SemanticLayerSourceClientImpl._parse_upload_response(response)

    assert result.sources["schema"].file_id == "file-old-1"
    assert result.sources["documentation"] is None
