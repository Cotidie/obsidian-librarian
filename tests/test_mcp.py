import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from obsidian_librarian import mcp_server, service
from obsidian_librarian.chunker import chunk_note
from obsidian_librarian.config import Config
from obsidian_librarian.index import VectorIndex
from obsidian_librarian.vault import iter_notes

ROOT = Path(__file__).resolve().parents[1]


# ---- offline index + subprocess helpers -------------------------------------

def _fake_build(vault: Path, db: Path) -> None:
    cfg = Config()
    cfg.vault_path = str(vault)
    cfg.index_path = str(db)
    notes = list(iter_notes(cfg))
    chunks, hashes = [], {}
    for n in notes:
        hashes[n.note_path] = n.note_hash
        chunks.extend(chunk_note(n.note_path, n.text, cfg))
    VectorIndex(cfg).build(chunks, [[0.0, 0, 0, 0]] * len(chunks), hashes)


def _server_env(vault: Path, db: Path, **extra) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}  # drop ROS leak
    env.update(VAULT_PATH=str(vault), VAULT_INDEX_PATH=str(db), **extra)
    return env


def _params(vault: Path, db: Path, **extra) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable, args=["-m", "obsidian_librarian.mcp_server"],
        env=_server_env(vault, db, **extra), cwd=str(ROOT))


# ---- unit: the iteration-3 learning (sync on launch, never per call) --------

def test_launch_syncs_once(monkeypatch):
    calls = []
    monkeypatch.setattr("obsidian_librarian.service.sync_on_launch", lambda cfg: calls.append(1))
    monkeypatch.setattr(mcp_server.mcp, "run", lambda **k: None)
    mcp_server.run()
    assert len(calls) == 1


def test_tool_does_not_sync(monkeypatch):
    synced = []
    monkeypatch.setattr("obsidian_librarian.service.sync_on_launch", lambda cfg: synced.append(1))
    monkeypatch.setattr("obsidian_librarian.service.search",
                        lambda cfg, q, k, mode: [{"note_path": "a.md", "breadcrumb": "b > a",
                                                  "text": "hello   world"}])
    out1 = mcp_server.search_vault("q")
    out2 = mcp_server.search_vault("q")
    assert synced == []  # the tool never reconciles
    assert out1 == out2 == [{"note_path": "a.md", "breadcrumb": "b > a", "snippet": "hello world"}]


# ---- unit: reindex_vault wraps the engine, stays alive on failure -----------

def test_reindex_incremental(monkeypatch):
    sentinel = {"full": False, "new": 1, "changed": 0, "deleted": 0, "chunks": 3}
    rebuilt = []
    monkeypatch.setattr("obsidian_librarian.service.sync", lambda cfg: sentinel)
    monkeypatch.setattr("obsidian_librarian.service.rebuild", lambda cfg: rebuilt.append(1))
    assert mcp_server.reindex_vault() == sentinel
    assert rebuilt == []  # incremental must not trigger a full rebuild


def test_reindex_full(monkeypatch):
    monkeypatch.setattr("obsidian_librarian.service.rebuild", lambda cfg: 42)
    assert mcp_server.reindex_vault(full=True) == {"full": True, "chunks": 42}


def test_reindex_error_does_not_raise(monkeypatch):
    def boom(cfg):
        raise RuntimeError("no VOYAGE_API_KEY")
    monkeypatch.setattr("obsidian_librarian.service.sync", boom)
    assert mcp_server.reindex_vault() == {"error": "no VOYAGE_API_KEY"}


# ---- subprocess: protocol works, stdout stays pure --------------------------

def test_server_lists_and_searches_offline(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "acr.md").write_text("## Capital\n\ncapital ratio CET1 KOSDAQ150 disclosure")
    db = tmp_path / "db"
    _fake_build(vault, db)

    async def go():
        # skip launch sync (offline); the pre-built index serves fts queries
        async with stdio_client(_params(vault, db, OBSIDIAN_LIBRARIAN_NO_SYNC="1")) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = await s.list_tools()
                names = {t.name for t in tools.tools}
                assert {"search_vault", "reindex_vault"} <= names
                res = await s.call_tool("search_vault", {"query": "KOSDAQ150", "mode": "fts"})
                blob = "".join(getattr(c, "text", "") or "" for c in res.content)
                assert "acr.md" in blob
    anyio.run(go)


def test_stdout_is_pure_jsonrpc(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "acr.md").write_text("## Capital\n\ncapital ratio CET1 KOSDAQ150 disclosure")
    db = tmp_path / "db"
    _fake_build(vault, db)  # in-sync index → launch sync is a no-op reconcile (offline)

    msgs = "\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "search_vault", "arguments": {"query": "KOSDAQ150", "mode": "fts"}}},
    ]) + "\n"

    proc = subprocess.run(
        [sys.executable, "-m", "obsidian_librarian.mcp_server"],
        input=msgs, capture_output=True, text=True, timeout=60,
        env=_server_env(vault, db), cwd=str(ROOT))  # no NO_SYNC: exercise the sync path

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, f"no stdout; stderr:\n{proc.stderr}"
    for ln in lines:  # every stdout line must be valid JSON-RPC, no library leakage
        json.loads(ln)
    assert "acr.md" in proc.stdout  # the tool call result came back on stdout


def test_reindex_vault_stdout_is_pure_jsonrpc(tmp_path):
    # Two notes, then delete one so the reindex is a deletion-only reconcile —
    # no embedding, so the tool path runs fully offline (no VOYAGE_API_KEY).
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "keep.md").write_text("## Keep\n\ncapital ratio CET1 disclosure")
    gone = vault / "gone.md"
    gone.write_text("## Gone\n\nKOSDAQ150 transient note")
    db = tmp_path / "db"
    _fake_build(vault, db)
    gone.unlink()  # vault now drifts: one deletion to reconcile

    msgs = "\n".join(json.dumps(m) for m in [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "reindex_vault", "arguments": {}}},
    ]) + "\n"

    proc = subprocess.run(
        [sys.executable, "-m", "obsidian_librarian.mcp_server"],
        input=msgs, capture_output=True, text=True, timeout=60,
        env=_server_env(vault, db, OBSIDIAN_LIBRARIAN_NO_SYNC="1"),  # isolate the tool's own sync
        cwd=str(ROOT))

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, f"no stdout; stderr:\n{proc.stderr}"
    for ln in lines:  # the mid-session reindex must not leak library output to stdout
        json.loads(ln)
    # the tool's reconcile summary rode back as the (non-error) result content
    assert '"isError":false' in proc.stdout and "deleted" in proc.stdout


@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY")
def test_search_vault_hybrid_end_to_end(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "n.md").write_text("## GARCH\n\nstructural break in variance regime")
    db = tmp_path / "db"

    async def go():
        async with stdio_client(_params(vault, db)) as (r, w):  # launch sync builds the index
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("search_vault", {"query": "regime shift variance"})
                blob = "".join(getattr(c, "text", "") or "" for c in res.content)
                assert "n.md" in blob
    anyio.run(go)
