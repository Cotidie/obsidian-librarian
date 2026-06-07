import os

import pytest
from click.testing import CliRunner

from obsidian_librarian.cli import main
from obsidian_librarian.config import Config
from obsidian_librarian.vault import iter_notes


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
