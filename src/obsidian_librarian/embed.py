import voyageai


class EmbeddingClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = voyageai.Client()  # reads VOYAGE_API_KEY from env

    def _embed(self, texts, input_type):
        # Voyage caps batch size/tokens per call; chunk into batches of 128.
        out = []
        for i in range(0, len(texts), 128):
            batch = texts[i:i + 128]
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
