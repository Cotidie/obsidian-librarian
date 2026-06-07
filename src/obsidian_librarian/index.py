import os

import lancedb


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
        # one-shot: drop and recreate (iter 1 has no incremental path)
        self.db.drop_table(self.cfg.table_name, ignore_missing=True)
        data = list(self._rows(chunks, vectors, note_hashes))
        self.db.create_table(self.cfg.table_name, data=data)

    def _table(self):
        return self.db.open_table(self.cfg.table_name)

    def count(self) -> int:
        return self._table().count_rows()

    def search(self, query_vector, k: int = 8) -> list[dict]:
        res = (self._table().search(list(query_vector))
               .metric("cosine").limit(k).to_list())
        for r in res:
            r.pop("vector", None)
        return res
