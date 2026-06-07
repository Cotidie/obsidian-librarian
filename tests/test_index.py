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
    hits = idx.search([0.9, 0.1, 0, 0], k=2)
    assert hits[0]["note_path"] == "a.md"
    assert {"note_path", "breadcrumb", "text", "chunk_index"} <= hits[0].keys()
