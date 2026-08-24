"""Promote the newest successful live-test Semantic Layer artifact for local use.

The live integration test writes timestamped artifacts below
``tests/integration/live/outputs``.  The local Text-to-SQL runtime instead
reads ``outputs/semantic_layer/approved_semantic_layer.json`` when
``AI_LOCAL_DEV_MODE=true``.  This script bridges those two locations.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


AI_ROOT = Path(__file__).resolve().parents[1]
TEST_ARTIFACT_ROOT = (
    AI_ROOT
    / "tests"
    / "integration"
    / "live"
    / "outputs"
    / "test_real_semantic_layer_generation_validation_review_and_indexing"
)
LOCAL_SEMANTIC_OUTPUT = AI_ROOT / "outputs" / "semantic_layer"
REQUIRED_ARTIFACTS = (
    "approved_semantic_layer.json",
    "validation_result.json",
    "review_result.json",
    "index_build_result.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote a successful live Semantic Layer test artifact for local runtime use."
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Specific timestamped live-test artifact directory. Defaults to the newest valid one.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the artifact that would be promoted without copying files.",
    )
    return parser.parse_args()


def is_successful_artifact(directory: Path) -> bool:
    if not directory.is_dir() or not all((directory / name).is_file() for name in REQUIRED_ARTIFACTS):
        return False

    try:
        approved = json.loads((directory / "approved_semantic_layer.json").read_text(encoding="utf-8"))
        validation = json.loads((directory / "validation_result.json").read_text(encoding="utf-8"))
        review = json.loads((directory / "review_result.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    metadata = approved.get("metadata", {}) if isinstance(approved, dict) else {}
    return (
        metadata.get("status") == "approved"
        and validation.get("status") == "passed"
        and str(review.get("decision", "")).casefold() == "approve"
    )


def find_latest_successful_artifact() -> Path:
    if not TEST_ARTIFACT_ROOT.is_dir():
        raise FileNotFoundError(f"Live-test artifact directory does not exist: {TEST_ARTIFACT_ROOT}")

    candidates = [path for path in TEST_ARTIFACT_ROOT.iterdir() if is_successful_artifact(path)]
    if not candidates:
        raise FileNotFoundError("No complete, approved live-test Semantic Layer artifact was found.")
    return max(candidates, key=lambda path: path.name)


def promote(source: Path, dry_run: bool) -> None:
    if not is_successful_artifact(source):
        raise ValueError(f"Artifact is incomplete or not approved: {source}")

    print(f"Source artifact: {source}")
    print(f"Local runtime destination: {LOCAL_SEMANTIC_OUTPUT}")
    if dry_run:
        print("Dry run: no files were copied.")
        return

    LOCAL_SEMANTIC_OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename in REQUIRED_ARTIFACTS:
        shutil.copy2(source / filename, LOCAL_SEMANTIC_OUTPUT / filename)

    for index_path in source.glob("*.faiss"):
        shutil.copy2(index_path, LOCAL_SEMANTIC_OUTPUT / index_path.name)
        metadata_path = index_path.with_suffix(index_path.suffix + ".metadata.json")
        if metadata_path.is_file():
            shutil.copy2(metadata_path, LOCAL_SEMANTIC_OUTPUT / metadata_path.name)

    print("Promoted approved Semantic Layer artifact successfully.")


def main() -> None:
    args = parse_args()
    source = args.artifact_dir.resolve() if args.artifact_dir else find_latest_successful_artifact()
    promote(source, args.dry_run)


if __name__ == "__main__":
    main()
