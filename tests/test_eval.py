import os
from pathlib import Path

import pytest

from obsidian_librarian import eval as ev
from obsidian_librarian.chunker import chunk_note
from obsidian_librarian.config import Config
from obsidian_librarian.index import VectorIndex
from obsidian_librarian.vault import iter_notes

EVAL = Path(__file__).parent / "eval"
CORPUS = EVAL / "corpus"
QUERIES = EVAL / "queries.yaml"


def _cfg(tmp_path):
    cfg = Config()
    cfg.vault_path = str(CORPUS)
    cfg.index_path = str(tmp_path / "db")
    return cfg


def _fake_build(cfg):
    """Index the corpus with zero vectors (no API) — enough for fts-only eval."""
    notes = list(iter_notes(cfg))
    chunks, hashes = [], {}
    for n in notes:
        hashes[n.note_path] = n.note_hash
        chunks.extend(chunk_note(n.note_path, n.text, cfg))
    VectorIndex(cfg).build(chunks, [[0.0, 0, 0, 0]] * len(chunks), hashes)


def test_fts_recall_on_exact_token_subsets_offline(tmp_path):
    cfg = _cfg(tmp_path)
    _fake_build(cfg)
    queries = ev.load_queries(QUERIES)
    for tag in ("acronym", "exact"):
        sub = ev.subset(queries, tag)
        r = ev.evaluate(cfg, sub, "fts", k=5)
        assert r["recall_at_k"] == 1.0, (tag, r["rows"])


@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY")
def test_hybrid_regression_baseline(tmp_path):
    cfg = _cfg(tmp_path)
    ev.build_index(cfg, _embedder(cfg))
    queries = ev.load_queries(QUERIES)
    hybrid = ev.evaluate(cfg, queries, "hybrid", k=5, embedder=_embedder(cfg))
    vector = ev.evaluate(cfg, queries, "vector", k=5, embedder=_embedder(cfg))
    # baseline: retrieval is currently strong — guard against regressions
    assert hybrid["recall_at_k"] >= 0.9, hybrid["rows"]
    assert hybrid["mrr"] >= 0.85, hybrid["rows"]
    # hybrid must never be worse than dense-only on this set
    assert hybrid["recall_at_k"] >= vector["recall_at_k"]
    assert hybrid["mrr"] >= vector["mrr"] - 1e-9


def _embedder(cfg):
    from obsidian_librarian.embed import EmbeddingClient
    return EmbeddingClient(cfg)
