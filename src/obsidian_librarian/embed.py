import voyageai

from .chunker import estimate_tokens

# Voyage caps each call by list length (1000) and total tokens per request
# (120K for voyage-4-large). Batch under both, with headroom; the token budget is
# the usual binding constraint. Sized for standard (paid) rate limits.
MAX_BATCH = 1000
TOKEN_BUDGET = 100000


def _batches(texts):
    batch, tokens = [], 0
    for t in texts:
        tt = estimate_tokens(t)
        if batch and (len(batch) >= MAX_BATCH or tokens + tt > TOKEN_BUDGET):
            yield batch
            batch, tokens = [], 0
        batch.append(t)
        tokens += tt
    if batch:
        yield batch


class EmbeddingClient:
    def __init__(self, cfg):
        self.cfg = cfg
        # max_retries lets the SDK back off on transient 429s instead of failing.
        self.client = voyageai.Client(max_retries=3)  # reads VOYAGE_API_KEY from env

    def _embed(self, texts, input_type):
        out = []
        for batch in _batches(texts):
            r = self.client.embed(batch, model=self.cfg.model,
                                  input_type=input_type,
                                  output_dimension=self.cfg.embed_dim,
                                  output_dtype="float")
            out.extend(r.embeddings)
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]
