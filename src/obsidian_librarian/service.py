"""Engine shared by the CLI and the MCP server: indexing, reconciliation, search.

Holds no presentation logic — callers format the returned data. Progress and
warnings go to stderr so a stdout-only JSON-RPC channel (the MCP server) stays
clean; the CLI inherits the same discipline harmlessly.
"""
import os

import click

from .chunker import chunk_note
from .embed import EmbeddingClient
from .index import VectorIndex
from .vault import iter_notes


def _notice(msg: str) -> None:
    click.echo(msg, err=True)


def _chunk_notes(notes, cfg):
    chunks, hashes = [], {}
    for note in notes:
        hashes[note.note_path] = note.note_hash
        chunks.extend(chunk_note(note.note_path, note.text, cfg))
    return chunks, hashes


def _embed_chunks(chunks, embedder):
    return embedder.embed_documents([f"{c.breadcrumb}\n\n{c.text}" for c in chunks])


def _full_build(cfg) -> int:
    notes = list(iter_notes(cfg))
    chunks, hashes = _chunk_notes(notes, cfg)
    vectors = _embed_chunks(chunks, EmbeddingClient(cfg))
    VectorIndex(cfg).build(chunks, vectors, hashes)
    return len(chunks)


def _apply_reconcile(idx, cfg, new, changed, deleted) -> int:
    """Delete dropped/changed notes, embed+add new/changed, rebuild FTS. Returns
    the number of chunks embedded. Constructs EmbeddingClient only when there is
    something to embed, so a deletion-only reconcile stays offline."""
    idx.delete_notes(deleted + [n.note_path for n in changed])
    chunks, hashes = _chunk_notes(new + changed, cfg)
    if chunks:
        idx.add_chunks(chunks, _embed_chunks(chunks, EmbeddingClient(cfg)), hashes)
    idx.rebuild_fts()  # always — also builds FTS on first sync over an iter-1 index
    return len(chunks)


def classify(cfg):
    """Diff the vault against the index by note_hash. Returns (idx, has_table, new, changed, deleted)."""
    notes = list(iter_notes(cfg))
    cur = {n.note_path: n.note_hash for n in notes}
    idx = VectorIndex(cfg)
    has = idx.has_table()
    indexed = idx.indexed_note_hashes() if has else {}
    new = [n for n in notes if n.note_path not in indexed]
    changed = [n for n in notes if n.note_path in indexed and cur[n.note_path] != indexed[n.note_path]]
    deleted = sorted(p for p in indexed if p not in cur)
    return idx, has, new, changed, deleted


def has_index(cfg) -> bool:
    return VectorIndex(cfg).has_table()


def rebuild(cfg) -> int:
    """Force a full rebuild of the index from scratch."""
    return _full_build(cfg)


def sync(cfg) -> dict:
    """Reconcile the index to the vault: full build if empty, else incremental.
    Raises on embedding failure (the explicit `--reindex` path wants to know)."""
    idx, has, new, changed, deleted = classify(cfg)
    if not has:
        return {"full": True, "chunks": _full_build(cfg)}
    chunks = _apply_reconcile(idx, cfg, new, changed, deleted)
    return {"full": False, "new": len(new), "changed": len(changed),
            "deleted": len(deleted), "chunks": chunks}


def auto_sync(cfg) -> dict | None:
    """Reconcile the index before a query. Returns None if no index exists yet,
    else {"reconciled": N}. Embeds only when notes were added/changed, so a
    deletion-only reconcile stays offline. Degrades to stale results (stderr
    warning) if embedding fails, e.g. an unavailable key."""
    idx, has, new, changed, deleted = classify(cfg)
    if not has:
        return None
    reconciled = len(new) + len(changed) + len(deleted)
    if reconciled == 0:
        return {"reconciled": 0}
    try:
        _apply_reconcile(idx, cfg, new, changed, deleted)
    except Exception as e:  # noqa: BLE001 — degrade, don't crash a query on a sync hiccup
        _notice(f"warning: auto-sync failed ({e}); results may be stale")
        return {"reconciled": 0}
    return {"reconciled": reconciled}


def sync_on_launch(cfg) -> dict:
    """One-shot reconcile for a server/session start: full build when no index
    exists, else an incremental reconcile. Logs to stderr and never raises — a
    Voyage outage degrades to serving the existing index, not a dead server.
    Set OBSIDIAN_LIBRARIAN_NO_SYNC=1 to skip (fast/offline launch)."""
    if os.environ.get("OBSIDIAN_LIBRARIAN_NO_SYNC"):
        _notice("sync skipped (OBSIDIAN_LIBRARIAN_NO_SYNC set)")
        return {"skipped": True}
    try:
        result = sync(cfg)
        if result.get("full"):
            _notice(f"indexed {result['chunks']} chunks from {cfg.vault_path} (full build)")
        else:
            _notice(f"synced: {result['new']} new, {result['changed']} changed, "
                    f"{result['deleted']} deleted, {result['chunks']} embedded")
        return result
    except Exception as e:  # noqa: BLE001 — a server must still start and serve
        _notice(f"warning: launch sync failed ({e}); serving the existing index")
        return {"error": str(e)}


def search(cfg, query: str, k: int = 8, mode: str = None) -> list[dict]:
    """Run a query against the index and return ranked hits (note_path, breadcrumb,
    text). Embeds the query only for vector/hybrid; fts stays offline."""
    mode = mode or cfg.search_mode
    qv = EmbeddingClient(cfg).embed_query(query) if mode in ("vector", "hybrid") else None
    return VectorIndex(cfg).search(query_vector=qv, query_text=query, k=k, mode=mode)
