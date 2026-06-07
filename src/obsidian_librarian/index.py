import os

import lancedb
from lancedb.rerankers import RRFReranker


class VectorIndex:
    def __init__(self, cfg):
        self.cfg = cfg
        os.makedirs(cfg.index_path, exist_ok=True)
        self.db = lancedb.connect(cfg.index_path)

    def _rows(self, chunks, vectors, note_hashes):
        for c, v in zip(chunks, vectors):
            yield {"vector": list(v), "note_path": c.note_path,
                   "breadcrumb": c.breadcrumb, "chunk_index": c.chunk_index,
                   "text": c.text, "note_hash": note_hashes.get(c.note_path, "")}

    def build(self, chunks, vectors, note_hashes):
        # one-shot full rebuild: drop, recreate, and (re)build the BM25 index
        self.db.drop_table(self.cfg.table_name, ignore_missing=True)
        data = list(self._rows(chunks, vectors, note_hashes))
        self.db.create_table(self.cfg.table_name, data=data)
        self.rebuild_fts()

    def rebuild_fts(self):
        # BM25 full-text index over the body column; native FTS is not auto-updated
        # on insert, so this is called after every build/sync.
        self._table().create_fts_index(self.cfg.fts_column, replace=True)

    def _table(self):
        return self.db.open_table(self.cfg.table_name)

    def count(self) -> int:
        return self._table().count_rows()

    def search(self, query_vector=None, query_text=None, k: int = 8,
               mode: str = None) -> list[dict]:
        t = self._table()
        mode = mode or self.cfg.search_mode
        if mode == "vector":
            q = t.search(list(query_vector)).metric("cosine").limit(k)
        elif mode == "fts":
            q = t.search(query_text, query_type="fts",
                         fts_columns=[self.cfg.fts_column]).limit(k)
        elif mode == "hybrid":
            q = (t.search(query_type="hybrid")
                 .vector(list(query_vector))
                 .text(query_text)
                 .rerank(RRFReranker())
                 .limit(k))
        else:
            raise ValueError(f"unknown search mode: {mode!r}")
        res = q.to_list()
        for r in res:
            r.pop("vector", None)
        return res
