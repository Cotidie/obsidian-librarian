import os
from dataclasses import dataclass, field

DEFAULT_VAULT = "/home/cotidie/repositories/cotidie/knowledge-base"
DEFAULT_INDEX = os.path.expanduser("~/.cache/obsidian-librarian/lancedb")


@dataclass
class Config:
    vault_path: str = field(default_factory=lambda: os.environ.get("VAULT_PATH", DEFAULT_VAULT))
    index_path: str = field(default_factory=lambda: os.environ.get("VAULT_INDEX_PATH", DEFAULT_INDEX))
    table_name: str = "chunks"
    model: str = "voyage-4-large"
    embed_dim: int = 1024            # Matryoshka; half of 2048, near-full quality, smaller index
    chunk_min_tokens: int = 80       # below this, merge with siblings / keep whole note
    chunk_max_tokens: int = 500      # above this, descend a heading level or paragraph-split
    overlap_sentences: int = 1       # overlap when paragraph-splitting an oversized leaf
    ignore_globs: tuple = ("98-Resources/templates/*", ".obsidian/*", ".git/*")
