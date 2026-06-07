import click

from .chunker import chunk_note
from .config import Config
from .embed import EmbeddingClient
from .index import VectorIndex
from .vault import iter_notes


def _reindex(cfg) -> int:
    notes = list(iter_notes(cfg))
    all_chunks, hashes = [], {}
    for n in notes:
        hashes[n.note_path] = n.note_hash
        all_chunks.extend(chunk_note(n.note_path, n.text, cfg))
    embedder = EmbeddingClient(cfg)
    texts = [f"{c.breadcrumb}\n\n{c.text}" for c in all_chunks]
    vectors = embedder.embed_documents(texts)
    VectorIndex(cfg).build(all_chunks, vectors, hashes)
    return len(all_chunks)


@click.command()
@click.argument("query", required=False)
@click.option("--reindex", is_flag=True, help="Rebuild the index from the vault.")
@click.option("--vault", default=None, help="Vault path override.")
@click.option("--k", default=8, help="Number of results.")
def main(query, reindex, vault, k):
    cfg = Config()
    if vault:
        cfg.vault_path = vault
    if reindex:
        n = _reindex(cfg)
        click.echo(f"Indexed {n} chunks from {cfg.vault_path}")
        if not query:
            return
    if not query:
        raise click.UsageError("Provide a QUERY, or --reindex.")
    qv = EmbeddingClient(cfg).embed_query(query)
    hits = VectorIndex(cfg).search(qv, k=k)
    for h in hits:
        click.echo(f"{h['note_path']}  [{h['breadcrumb']}]")
        snippet = h["text"].replace("\n", " ")[:160]
        click.echo(f"    {snippet}")
