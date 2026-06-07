"""Lightweight retrieval evaluation: query -> expected note, scored by Recall@k and MRR.

Runs over a small committed corpus so it is deterministic and repeatable, independent
of any private vault. `fts` mode is offline; `vector`/`hybrid` need an embedder.
"""
from pathlib import Path

import yaml

from .chunker import chunk_note
from .index import VectorIndex
from .vault import iter_notes


def load_queries(path) -> list[dict]:
    return yaml.safe_load(Path(path).read_text())


def build_index(cfg, embedder) -> int:
    """Embed and index every note under cfg.vault_path (the eval corpus)."""
    notes = list(iter_notes(cfg))
    chunks, hashes = [], {}
    for n in notes:
        hashes[n.note_path] = n.note_hash
        chunks.extend(chunk_note(n.note_path, n.text, cfg))
    vectors = embedder.embed_documents([f"{c.breadcrumb}\n\n{c.text}" for c in chunks])
    VectorIndex(cfg).build(chunks, vectors, hashes)
    return len(chunks)


def _ranked_notes(hits) -> list[str]:
    """Reduce chunk hits to an ordered list of unique note paths (note-level ranking)."""
    out = []
    for h in hits:
        if h["note_path"] not in out:
            out.append(h["note_path"])
    return out


def evaluate(cfg, queries, mode, k=5, embedder=None) -> dict:
    idx = VectorIndex(cfg)
    n = len(queries)
    recall = 0.0
    rr = 0.0
    rows = []
    for q in queries:
        qtext, expect = q["query"], q["expect"]
        qv = embedder.embed_query(qtext) if (mode in ("vector", "hybrid") and embedder) else None
        hits = idx.search(query_vector=qv, query_text=qtext, k=k, mode=mode)
        notes = _ranked_notes(hits)
        rank = notes.index(expect) + 1 if expect in notes else 0
        recall += 1.0 if rank else 0.0
        rr += (1.0 / rank) if rank else 0.0
        rows.append({"query": qtext, "expect": expect, "rank": rank})
    return {"mode": mode, "k": k, "n": n,
            "recall_at_k": recall / n if n else 0.0,
            "mrr": rr / n if n else 0.0,
            "rows": rows}


def subset(queries, tag) -> list[dict]:
    return [q for q in queries if tag in (q.get("tags") or [])]
