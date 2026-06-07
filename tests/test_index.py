from obsidian_librarian.chunker import Chunk
from obsidian_librarian.config import Config
from obsidian_librarian.index import VectorIndex


def _cfg(tmp_path):
    c = Config()
    c.index_path = str(tmp_path / "db")
    c.embed_dim = 4
    return c


def _rows():
    chunks = [Chunk("a.md", "a > X", 0, "alpha"),
              Chunk("b.md", "b > Y", 0, "beta")]
    vecs = [[1.0, 0, 0, 0], [0, 1.0, 0, 0]]
    return chunks, vecs


def test_build_then_count(tmp_path):
    cfg = _cfg(tmp_path)
    idx = VectorIndex(cfg)
    chunks, vecs = _rows()
    idx.build(chunks, vecs, note_hashes={"a.md": "h1", "b.md": "h2"})
    assert idx.count() == 2


def test_search_returns_nearest_first(tmp_path):
    cfg = _cfg(tmp_path)
    idx = VectorIndex(cfg)
    chunks, vecs = _rows()
    idx.build(chunks, vecs, note_hashes={"a.md": "h1", "b.md": "h2"})
    hits = idx.search(query_vector=[0.9, 0.1, 0, 0], k=2, mode="vector")
    assert hits[0]["note_path"] == "a.md"
    assert {"note_path", "breadcrumb", "text", "chunk_index"} <= hits[0].keys()


def test_fts_finds_rare_token(tmp_path):
    cfg = _cfg(tmp_path)
    idx = VectorIndex(cfg)
    chunks = [Chunk("plain.md", "plain > A", 0, "general notes about the weather and lunch"),
              Chunk("acr.md", "acr > Capital", 0, "capital ratio CET1 KOSDAQ150 disclosure")]
    vecs = [[1.0, 0, 0, 0], [0, 1.0, 0, 0]]
    idx.build(chunks, vecs, note_hashes={"plain.md": "h1", "acr.md": "h2"})
    hits = idx.search(query_text="KOSDAQ150", k=3, mode="fts")
    assert hits[0]["note_path"] == "acr.md"


def test_hybrid_returns_both_signals(tmp_path):
    cfg = _cfg(tmp_path)
    idx = VectorIndex(cfg)
    chunks = [Chunk("a.md", "a > X", 0, "alpha apple semantics"),
              Chunk("b.md", "b > Y", 0, "beta KOSDAQ150 disclosure")]
    vecs = [[1.0, 0, 0, 0], [0, 1.0, 0, 0]]
    idx.build(chunks, vecs, note_hashes={"a.md": "h1", "b.md": "h2"})
    # vector favors a.md, keyword favors b.md — hybrid should surface both
    hits = idx.search(query_vector=[1.0, 0, 0, 0], query_text="KOSDAQ150", k=2, mode="hybrid")
    paths = {h["note_path"] for h in hits}
    assert {"a.md", "b.md"} <= paths
