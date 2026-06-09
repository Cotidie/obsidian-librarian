<p align="center">
  <img src="docs/cover.png" alt="Obsidian Librarian" width="100%">
</p>

# Obsidian Librarian

Semantic search for your Obsidian vault, straight from Claude.

Obsidian Librarian is an MCP server that gives Claude semantic search over your
Obsidian notes. It indexes your vault's Markdown files and exposes search and
reindex tools, so Claude can find the right notes mid-conversation.

It turns your vault into a true second brain: ask a question in
plain language and get back the notes that actually answer it, ranked by what
they mean rather than the exact words you typed. A search for "volatility regime
change" will surface a note about "GARCH structural breaks" even if your wording
never appears in it.

The goal is a self-growing knowledge base. Because Claude can both search the
vault and write to it, your notes stop being a static archive: Claude finds what
you already know, fills the gaps, and links new notes back in, so the vault keeps
getting richer the more you use it.

## Features

- **Meaning Based Search:** Ask in plain language, get notes ranked by what they mean.
- **Indexing .md Notes:** Scans vault's Markdown notes, builds searchable index of their content.
- **Auto Reindexing:** Reindex re-reads only notes that changed, keeping index fresh cheaply.

## Prerequisites

- **[Claude Code](https://claude.com/claude-code)**: runs the MCP server.
- **Obsidian vault**: Markdown notes you want to search.
- **[uv](https://docs.astral.sh/uv/) and Python 3.13**: run the project.
- **[Voyage API key](https://www.voyageai.com/)**: powers meaning-based search.

## Setup

Register Obsidian Librarian with Claude as a user-scope MCP server (available in
every session):

```bash
claude mcp add obsidian-librarian --scope user \
  -e VOYAGE_API_KEY=your-voyage-key \
  -e VAULT_PATH=/path/to/your/vault \
  -- uv run --directory /path/to/obsidian-librarian obsidian-librarian
```

That's it. Now just ask Claude in plain language:

> Search my vault for notes on volatility regime change

## MCP tools

Once registered, Claude can call two tools on your vault.

### `search_vault(query, k=8, mode="hybrid")`

Searches the vault by meaning and keyword. Returns up to `k` ranked chunks, each
with the note path, a `folder > title > heading` breadcrumb, and the chunk text.

- `query`: natural-language question or keywords (English, Korean, or mixed).
- `k`: number of results to return. Default `8`.
- `mode`: `"hybrid"` (default), `"vector"` (meaning only), or `"fts"` (keywords,
  offline).

```text
search_vault("volatility regime change", k=5, mode="vector")
```

### `reindex_vault(full=False)`

Reconciles the search index with the vault on disk. Call after creating or
editing notes; `search_vault` does not auto-refresh during a session. Returns a
summary of what changed.

- `full`: `False` (default) embeds only new or changed notes (cheap). `True`
  forces a full rebuild from scratch (use only if the index looks corrupt).

```text
reindex_vault()           # cheap incremental sync
reindex_vault(full=True)  # full rebuild
```

The index lives at `~/.cache/obsidian-librarian/`, outside your vault. Delete
that folder for a clean slate.

## Development

```bash
uv run pytest
```

Embedding tests skip without `VOYAGE_API_KEY`; the rest always run.

> If your shell sources ROS (a leaked `PYTHONPATH`), prefix commands with
> `env -u PYTHONPATH`, e.g. `env -u PYTHONPATH uv run pytest`.
