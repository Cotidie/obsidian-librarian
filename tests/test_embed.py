import math
import os

import pytest

from obsidian_librarian.config import Config
from obsidian_librarian.embed import EmbeddingClient

pytestmark = pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"),
                                reason="needs VOYAGE_API_KEY")


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


def test_dim_and_cosine_sanity():
    c = EmbeddingClient(Config())
    docs = c.embed_documents(["GARCH structural break in volatility",
                              "today's lunch menu was bibimbap"])
    assert len(docs[0]) == Config().embed_dim
    q = c.embed_query("variance regime shift")
    assert _cos(q, docs[0]) > _cos(q, docs[1])
