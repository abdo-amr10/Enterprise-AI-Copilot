from pathlib import Path

from src import cli


def test_ensure_local_semantic_index_builds_only_when_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AI_LOCAL_DEV_MODE", "true")
    monkeypatch.setattr(cli, "LOCAL_SEMANTIC_OUTPUT", tmp_path)

    built = []

    def build_index() -> None:
        built.append(True)
        index_path = tmp_path / "semantic_index.faiss"
        index_path.write_bytes(b"index")
        index_path.with_suffix(".faiss.metadata.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("scripts.build_semantic_index.main", build_index)

    cli.ensure_local_semantic_index()
    cli.ensure_local_semantic_index()

    assert built == [True]


def test_ensure_local_semantic_index_skips_non_local_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("AI_LOCAL_DEV_MODE", raising=False)
    monkeypatch.setattr(cli, "LOCAL_SEMANTIC_OUTPUT", Path(tmp_path))

    monkeypatch.setattr(
        "scripts.build_semantic_index.main",
        lambda: (_ for _ in ()).throw(AssertionError("must not build")),
    )

    cli.ensure_local_semantic_index()
