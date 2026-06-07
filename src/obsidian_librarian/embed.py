import voyageai

from .chunker import estimate_tokens

# Voyage caps each call by list length and total tokens. Keep batches under both:
# 128 texts max, and a token budget that fits the free tier's 10K TPM ceiling.
MAX_BATCH = 128
TOKEN_BUDGET = 8000


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
        # max_retries lets the SDK back off on 429s instead of failing immediately.
        self.client = voyageai.Client(max_retries=5)  # reads VOYAGE_API_KEY from env

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
