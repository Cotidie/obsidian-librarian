"""stdio MCP server exposing the vault as a `search_vault` tool to Claude Code.

stdout is the JSON-RPC channel, so it must stay pure: any stray write — ours or a
library's (`lancedb`/`voyageai`) — corrupts the protocol. Two guards enforce that:
all logging is routed to stderr, and the one phase that runs noisy library code
(the launch sync) has its stdout file descriptor redirected to stderr.

The index is reconciled once, at launch — not per query. An MCP session fires many
`search_vault` calls; per-call sync would re-scan/re-embed wastefully.
"""
import logging
import os
import sys
from contextlib import contextmanager

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from . import service
from .config import Config

mcp = FastMCP("obsidian-librarian")
cfg = Config()


@mcp.tool()
def search_vault(query: str, k: int = 8, mode: str = "hybrid") -> list[dict]:
    """Search the user's Obsidian vault by meaning and keyword (hybrid).

    Use this to find existing notes before answering from memory or creating new
    ones. Returns up to `k` ranked chunks, each with the note path, a
    `folder > title > heading` breadcrumb, and the chunk text.

    Args:
        query: Natural-language question or keywords (English, Korean, or mixed).
        k: Number of results to return.
        mode: "hybrid" (default), "vector" (meaning only), or "fts" (keywords, offline).
    """
    hits = service.search(cfg, query, k, mode)
    return [{"note_path": h["note_path"], "breadcrumb": h["breadcrumb"],
             "snippet": " ".join(h["text"].split())[:400]} for h in hits]


def _configure_stderr_logging() -> None:
    """Route our logging and noisy libraries to stderr (never stdout)."""
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    for name in ("lancedb", "voyageai", "httpx", "httpcore"):
        logging.getLogger(name).addHandler(logging.StreamHandler(sys.stderr))


@contextmanager
def _stdout_to_stderr():
    """Redirect the stdout file descriptor to stderr for the duration of the block,
    so any library that writes to fd 1 directly can't corrupt the JSON-RPC stream."""
    saved = os.dup(1)
    try:
        os.dup2(2, 1)
        yield
    finally:
        os.dup2(saved, 1)
        os.close(saved)


def run() -> None:
    load_dotenv()
    _configure_stderr_logging()
    with _stdout_to_stderr():  # the launch sync is the one phase that runs noisy library code
        service.sync_on_launch(cfg)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
