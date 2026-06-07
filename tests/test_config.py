from obsidian_librarian.config import Config


def test_defaults_present():
    c = Config()
    assert c.model == "voyage-4-large"
    assert c.embed_dim == 1024
    assert c.chunk_max_tokens >= c.chunk_min_tokens > 0
    assert c.vault_path.endswith("knowledge-base")
    assert "lancedb" in c.index_path
    assert "templates" in " ".join(c.ignore_globs)
