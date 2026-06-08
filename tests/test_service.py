import os

import pytest

from obsidian_librarian import service
from obsidian_librarian.chunker import chunk_note
from obsidian_librarian.config import Config
from obsidian_librarian.index import VectorIndex
from obsidian_librarian.vault import iter_notes


class _Boom:
    def __init__(self, *a, **k):
        raise AssertionError("embedding client must not be constructed in this path")


def _fake_cfg(vault, index_dir) -> Config:
    """Config pointing at `vault` with an isolated index dir (no env needed)."""
    cfg = Config()
    cfg.vault_path = str(vault)
    cfg.index_path = str(index_dir)
    return cfg


def _fake_build(cfg) -> None:
    """Build an index with zero vectors (no API) for offline engine tests."""
    notes = list(iter_notes(cfg))
    chunks, hashes = [], {}
    for n in notes:
        hashes[n.note_path] = n.note_hash
        chunks.extend(chunk_note(n.note_path, n.text, cfg))
    VectorIndex(cfg).build(chunks, [[0.0, 0, 0, 0]] * len(chunks), hashes)


def test_search_fts_is_offline(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "acr.md").write_text("## Capital\n\ncapital ratio CET1 KOSDAQ150 disclosure")
    cfg = _fake_cfg(vault, tmp_path / "db")
    _fake_build(cfg)
    monkeypatch.setattr("obsidian_librarian.service.EmbeddingClient", _Boom)
    hits = service.search(cfg, "KOSDAQ150", k=5, mode="fts")
    assert any(h["note_path"] == "acr.md" for h in hits)


def test_auto_sync_returns_none_without_index(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\nbody")
    cfg = _fake_cfg(vault, tmp_path / "db")  # never built
    assert service.auto_sync(cfg) is None
    assert service.has_index(cfg) is False


def test_auto_sync_noop_when_in_sync(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\nbody text here")
    cfg = _fake_cfg(vault, tmp_path / "db")
    _fake_build(cfg)
    monkeypatch.setattr("obsidian_librarian.service.EmbeddingClient", _Boom)
    assert service.auto_sync(cfg) == {"reconciled": 0}


def test_auto_sync_drops_deleted_offline(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "keep.md").write_text("## Keep\n\nalpha stays")
    (vault / "gone.md").write_text("## Gone\n\nuniquetoken vanishes")
    cfg = _fake_cfg(vault, tmp_path / "db")
    _fake_build(cfg)

    (vault / "gone.md").unlink()
    monkeypatch.setattr("obsidian_librarian.service.EmbeddingClient", _Boom)
    assert service.auto_sync(cfg) == {"reconciled": 1}
    hits = service.search(cfg, "uniquetoken", k=5, mode="fts")
    assert all(h["note_path"] != "gone.md" for h in hits)


def test_sync_on_launch_skips_with_env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\nbody")
    cfg = _fake_cfg(vault, tmp_path / "db")
    monkeypatch.setenv("OBSIDIAN_LIBRARIAN_NO_SYNC", "1")
    monkeypatch.setattr("obsidian_librarian.service.EmbeddingClient", _Boom)
    assert service.sync_on_launch(cfg) == {"skipped": True}


def test_sync_on_launch_degrades_on_failure(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\nbody")
    cfg = _fake_cfg(vault, tmp_path / "db")

    def boom(_cfg):
        raise RuntimeError("voyage down")
    monkeypatch.setattr("obsidian_librarian.service.sync", boom)
    result = service.sync_on_launch(cfg)  # must not raise
    assert "error" in result


@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY")
def test_sync_on_launch_full_build_then_search(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## GARCH\n\nstructural break in variance regime")
    cfg = _fake_cfg(vault, tmp_path / "db")
    r = service.sync_on_launch(cfg)
    assert r.get("full") is True
    hits = service.search(cfg, "regime shift variance", k=5, mode="hybrid")
    assert any(h["note_path"] == "n.md" for h in hits)
