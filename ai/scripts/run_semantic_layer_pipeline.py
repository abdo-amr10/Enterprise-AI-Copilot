"""Run the local Semantic Layer build, review, and indexing workflow.

This development path deliberately has no Backend dependency. Human review
remains required; only the approved artifact is indexed for runtime.
"""

from __future__ import annotations

import argparse

def main(semantic_layer_id: str | None = None) -> None:
    from build_semantic_layer import main as build_draft
    from build_semantic_index import main as build_index
    from validate_and_review import main as validate_and_review

    build_draft(semantic_layer_id)
    validate_and_review()
    build_index()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic-layer-id")
    args = parser.parse_args()
    main(args.semantic_layer_id)
