"""Run the semantic-layer ingestion and initial-draft build flow."""

import argparse
import json
from pathlib import Path
from typing import Any

from src.application.dto.semantic_layer.semantic_layer_build_input import (
    SemanticLayerBuildInput,
)
from src.application.services.semantic_layer.builders.full_build_builder import (
    FullRebuildBuilder,
)
from src.application.services.semantic_layer.semantic_layer_identity_service import (
    SemanticLayerIdentityService,
)
from src.application.services.semantic_layer.semantic_layer_metadata_generator import (
    SemanticLayerMetadataService,
)
from src.infrastructure.llm.model_config import SEMANTIC_LAYER_CONFIG
from src.infrastructure.llm.ollama_client import OllamaClient
from src.infrastructure.semantic_layer.ingestion.schema_loader import SchemaLoader
from src.infrastructure.semantic_layer.ingestion.schema_mapper import SchemaMapper
from src.infrastructure.semantic_layer.ingestion.sources.optional_source_loader import (
    OptionalSourceLoader,
)
from src.infrastructure.semantic_layer.persistence.semantic_layer_id_generator import (
    SemanticLayerIdGenerator,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_METADATA_DIR = PROJECT_ROOT / "docs" / "database_metadata"

SCHEMA_PATH = DATABASE_METADATA_DIR / "schema.json"
DOCUMENTATION_PATH = DATABASE_METADATA_DIR / "documentation.md"
BUSINESS_GLOSSARY_PATH = DATABASE_METADATA_DIR / "business_glossary.md"
SAMPLE_DATA_PATH = DATABASE_METADATA_DIR / "sample_data.json"


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from a file.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON object.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON root is not an object.
    """
    if not path.exists():
        raise FileNotFoundError(f"Required source file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in: {path}")

    return data


def _load_sample_data(path: Path) -> dict[str, Any] | None:
    """Load optional sample data when available.

    Args:
        path: Path to the optional sample-data file.

    Returns:
        Parsed sample data, or None when the source is unavailable.
    """
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def main(semantic_layer_id: str | None = None) -> None:
    """Build the initial semantic-layer draft from database metadata."""

    # 1. Load the required schema source.
    raw_schema = _load_json(SCHEMA_PATH)

    # 2. Normalize and validate the required schema.
    schema_loader = SchemaLoader()
    normalized_schema = schema_loader.load(raw_schema)

    # 3. Extract the relationship metadata from the same schema source.
    relationship_metadata = raw_schema.get("relationships", [])

    if not isinstance(relationship_metadata, list):
        raise ValueError(
        "The 'relationships' field in schema.json must be a list."
    )

    # 4. Map explicitly provided relationships.
    schema_mapper = SchemaMapper()
    relationships = schema_mapper.map_relationships(
        relationship_metadata
    )

    # 5. Load optional documentation and business glossary.
    optional_source_loader = OptionalSourceLoader()

    optional_sources = optional_source_loader.load(
        documentation_path=DOCUMENTATION_PATH,
        business_glossary_path=BUSINESS_GLOSSARY_PATH,
    )

    # 6. Load optional sample data.
    sample_data = _load_sample_data(SAMPLE_DATA_PATH)

    # 7. Build the application-level input.
    build_input = SemanticLayerBuildInput(
        schema=normalized_schema,
        relationships=relationships,
        documentation=optional_sources["documentation"],
        business_glossary=optional_sources["business_glossary"],
        sample_data=sample_data,
    )

    # 8. Wire the configured LLM client into the application service.
    llm_client = OllamaClient(SEMANTIC_LAYER_CONFIG)
    builder = FullRebuildBuilder(llm_client)

    # 9. Generate the initial semantic-layer draft.
    result = builder.build(build_input)
    id_generator = SemanticLayerIdGenerator()
    draft = SemanticLayerMetadataService(id_generator).initialize(
        result.semantic_layer,
        semantic_layer_id or id_generator.generate_semantic_layer_id(),
    )
    draft = SemanticLayerIdentityService().assign_object_ids(draft)

    # 10. Save the generated draft.
    output_path = Path("outputs/semantic_layer/initial_draft.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(
            draft,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Initial semantic layer draft saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-layer-id")
    args = parser.parse_args()
    main(args.semantic_layer_id)
