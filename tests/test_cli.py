import os

import pytest
from click.testing import CliRunner

from obsidian_librarian.chunker import chunk_note
from obsidian_librarian.cli import main
from obsidian_librarian.config import Config
from obsidian_librarian.index import VectorIndex
from obsidian_librarian.vault import iter_notes


def _fake_build(vault, tmp_path, monkeypatch):
    """Build an index for `vault` with zero vectors (no API) at a temp index path."""
    monkeypatch.setenv("VAULT_INDEX_PATH", str(tmp_path / "db"))
    cfg = Config()
    cfg.vault_path = str(vault)
    notes = list(iter_notes(cfg))
    chunks, hashes = [], {}
    for n in notes:
        hashes[n.note_path] = n.note_hash
        chunks.extend(chunk_note(n.note_path, n.text, cfg))
    VectorIndex(cfg).build(chunks, [[0.0, 0, 0, 0]] * len(chunks), hashes)


class _Boom:
    def __init__(self, *a, **k):
        raise AssertionError("embedding client must not be constructed in this path")


def test_iter_notes_skips_ignored(tmp_path):
    (tmp_path / "00-Inbox").mkdir()
    (tmp_path / "00-Inbox" / "memo.md").write_text("hello")
    (tmp_path / "98-Resources" / "templates").mkdir(parents=True)
    (tmp_path / "98-Resources" / "templates" / "T.md").write_text("<% tp %>")
    cfg = Config()
    cfg.vault_path = str(tmp_path)
    paths = {n.note_path for n in iter_notes(cfg)}
    assert "00-Inbox/memo.md" in paths
    assert all("templates" not in p for p in paths)


@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY")
def test_end_to_end_reindex_and_query(tmp_path, monkeypatch):
    (tmp_path / "n.md").write_text("## GARCH\n\nstructural break in variance regime")
    monkeypatch.setenv("VAULT_INDEX_PATH", str(tmp_path / "db"))
    r = CliRunner().invoke(main, ["--vault", str(tmp_path), "--reindex",
                                  "regime shift variance"])
    assert r.exit_code == 0
    assert "n.md" in r.output


def test_status_reports_drift(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\nbody text here")
    _fake_build(vault, tmp_path, monkeypatch)

    r = CliRunner().invoke(main, ["--vault", str(vault), "--status"])
    assert r.exit_code == 0, r.output
    assert "IN SYNC" in r.output

    (vault / "n.md").write_text("## A\n\ncompletely different body")
    r2 = CliRunner().invoke(main, ["--vault", str(vault), "--status"])
    assert "changed" in r2.output


def test_fts_query_is_offline(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "acr.md").write_text("## Capital\n\ncapital ratio CET1 KOSDAQ150 disclosure")
    _fake_build(vault, tmp_path, monkeypatch)
    # fts must not construct the embedding client
    monkeypatch.setattr("obsidian_librarian.cli.EmbeddingClient", _Boom)
    r = CliRunner().invoke(main, ["--vault", str(vault), "--mode", "fts", "KOSDAQ150"])
    assert r.exit_code == 0, r.output
    assert "acr.md" in r.output


def test_query_without_index_errors(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\nbody text")
    monkeypatch.setenv("VAULT_INDEX_PATH", str(tmp_path / "db"))  # never built
    monkeypatch.setattr("obsidian_librarian.cli.EmbeddingClient", _Boom)
    r = CliRunner().invoke(main, ["--vault", str(vault), "anything"])
    assert r.exit_code != 0
    assert "No index yet" in r.output


def test_auto_sync_drops_deleted_offline(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "keep.md").write_text("## Keep\n\nalpha content stays here")
    (vault / "gone.md").write_text("## Gone\n\nuniquetoken zeta about to vanish")
    _fake_build(vault, tmp_path, monkeypatch)

    (vault / "gone.md").unlink()
    # deletion reconcile embeds nothing, so it must stay offline
    monkeypatch.setattr("obsidian_librarian.cli.EmbeddingClient", _Boom)
    r = CliRunner().invoke(main, ["--vault", str(vault), "--mode", "fts", "uniquetoken"])
    assert r.exit_code == 0, r.output
    assert "gone.md" not in r.output


def test_no_sync_skips_reconcile(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\ncapital ratio body text")
    _fake_build(vault, tmp_path, monkeypatch)

    def boom_sync(cfg):
        raise RuntimeError("auto-sync must be skipped with --no-sync")
    monkeypatch.setattr("obsidian_librarian.cli._auto_sync", boom_sync)

    r = CliRunner().invoke(main, ["--vault", str(vault), "--no-sync", "--mode", "fts", "capital"])
    assert r.exit_code == 0, r.output
    # without --no-sync the same monkeypatch fires, proving auto-sync is wired
    r2 = CliRunner().invoke(main, ["--vault", str(vault), "--mode", "fts", "capital"])
    assert r2.exit_code != 0


@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY")
def test_auto_sync_reembeds_edit(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## A\n\noriginal note about alpha")
    monkeypatch.setenv("VAULT_INDEX_PATH", str(tmp_path / "db"))

    r1 = CliRunner().invoke(main, ["--vault", str(vault), "--reindex"])
    assert r1.exit_code == 0, r1.output

    (vault / "n.md").write_text("## A\n\noriginal note about zxqphrase")
    r2 = CliRunner().invoke(main, ["--vault", str(vault), "zxqphrase"])
    assert r2.exit_code == 0, r2.output
    assert "n.md" in r2.output
    assert "auto-synced" in r2.stderr


@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY")
def test_reindex_incremental_zero_reembed(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "a.md").write_text("## A\n\nfirst note about alpha")
    (vault / "b.md").write_text("## B\n\nsecond note about beta")
    monkeypatch.setenv("VAULT_INDEX_PATH", str(tmp_path / "db"))

    r1 = CliRunner().invoke(main, ["--vault", str(vault), "--reindex"])
    assert r1.exit_code == 0, r1.output
    assert "full build" in r1.output

    r2 = CliRunner().invoke(main, ["--vault", str(vault), "--reindex"])
    assert r2.exit_code == 0, r2.output
    assert "0 chunks embedded" in r2.output

    (vault / "a.md").write_text("## A\n\nfirst note rewritten about gamma")
    r3 = CliRunner().invoke(main, ["--vault", str(vault), "--reindex"])
    assert r3.exit_code == 0, r3.output
    assert "1 changed" in r3.output
    assert "0 chunks embedded" not in r3.output
