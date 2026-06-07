import click
from dotenv import load_dotenv

from .chunker import chunk_note
from .config import Config
from .embed import EmbeddingClient
from .index import VectorIndex
from .vault import iter_notes


def _chunk_notes(notes, cfg):
    chunks, hashes = [], {}
    for note in notes:
        hashes[note.note_path] = note.note_hash
        chunks.extend(chunk_note(note.note_path, note.text, cfg))
    return chunks, hashes


def _embed_chunks(chunks, embedder):
    return embedder.embed_documents([f"{c.breadcrumb}\n\n{c.text}" for c in chunks])


def _full_build(cfg, embedder) -> int:
    notes = list(iter_notes(cfg))
    chunks, hashes = _chunk_notes(notes, cfg)
    vectors = _embed_chunks(chunks, embedder)
    VectorIndex(cfg).build(chunks, vectors, hashes)
    return len(chunks)


def _classify(cfg):
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


def _sync(cfg, embedder) -> dict:
    idx, has, new, changed, deleted = _classify(cfg)
    if not has:
        return {"full": True, "chunks": _full_build(cfg, embedder)}
    idx.delete_notes(deleted + [n.note_path for n in changed])
    chunks, hashes = _chunk_notes(new + changed, cfg)
    if chunks:
        idx.add_chunks(chunks, _embed_chunks(chunks, embedder), hashes)
    idx.rebuild_fts()  # always — also builds FTS on first sync over an iter-1 index
    return {"full": False, "new": len(new), "changed": len(changed),
            "deleted": len(deleted), "chunks": len(chunks)}


def _status(cfg) -> None:
    _, has, new, changed, deleted = _classify(cfg)
    if not has:
        raise click.UsageError("No index yet. Run --reindex first.")
    if not (new or changed or deleted):
        click.echo("IN SYNC")
        return
    click.echo("STALE — run --reindex")
    for n in new:
        click.echo(f"  added:   {n.note_path}")
    for n in changed:
        click.echo(f"  changed: {n.note_path}")
    for p in deleted:
        click.echo(f"  deleted: {p}")


@click.command()
@click.argument("query", required=False)
@click.option("--reindex", is_flag=True, help="Incrementally sync the index (embed only changed notes).")
@click.option("--rebuild", is_flag=True, help="Force a full rebuild of the index.")
@click.option("--status", "status", is_flag=True, help="Show index drift vs the vault (read-only, no embedding).")
@click.option("--mode", type=click.Choice(["vector", "fts", "hybrid"]), default=None,
              help="Search mode. Default from config (hybrid). 'fts' is offline.")
@click.option("--vault", default=None, help="Vault path override.")
@click.option("--k", default=8, help="Number of results.")
def main(query, reindex, rebuild, status, mode, vault, k):
    load_dotenv()  # VOYAGE_API_KEY / VAULT_PATH from a .env in the project root
    cfg = Config()
    if vault:
        cfg.vault_path = vault

    did_index = False
    if rebuild:
        n = _full_build(cfg, EmbeddingClient(cfg))
        click.echo(f"Rebuilt index: {n} chunks from {cfg.vault_path}")
        did_index = True
    elif reindex:
        r = _sync(cfg, EmbeddingClient(cfg))
        if r["full"]:
            click.echo(f"Indexed {r['chunks']} chunks from {cfg.vault_path} (full build)")
        else:
            click.echo(f"Synced: {r['new']} new, {r['changed']} changed, "
                       f"{r['deleted']} deleted, {r['chunks']} chunks embedded")
        did_index = True
    elif status:
        _status(cfg)
        return

    if not query:
        if did_index:
            return
        raise click.UsageError("Provide a QUERY, or use --reindex / --rebuild / --status.")

    mode = mode or cfg.search_mode
    qv = EmbeddingClient(cfg).embed_query(query) if mode in ("vector", "hybrid") else None
    hits = VectorIndex(cfg).search(query_vector=qv, query_text=query, k=k, mode=mode)
    for h in hits:
        click.echo(f"{h['note_path']}  [{h['breadcrumb']}]")
        snippet = h["text"].replace("\n", " ")[:160]
        click.echo(f"    {snippet}")
