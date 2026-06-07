# obsidian-librarian

Semantic search and synthesis over an Obsidian vault. Embeds notes with
[Voyage](https://www.voyageai.com/) (`voyage-4-large`), stores vectors in an
embedded [LanceDB](https://lancedb.com/) table, and answers meaning-based
queries from the terminal — later wrapped as an `obsidian-librarian` MCP server
for Claude Code.

## Status

CLI-first, built in vertical iterations. See [`docs/plans/`](docs/plans/):

- [`01-semantic-search-iteration-roadmap.md`](docs/plans/01-semantic-search-iteration-roadmap.md) — the 7-iteration roadmap (dense search → hybrid → sync → MCP → synthesis rule → image describe-to-text → Docker).
- [`02-iteration-1-search-cli.md`](docs/plans/02-iteration-1-search-cli.md) — implementation plan for iteration 1, the `vault-search` CLI.

## Setup

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
export VOYAGE_API_KEY="your-key"
```

## Usage

```bash
uv run vault-search --reindex            # one-shot bulk index (persisted to ~/.cache)
uv run vault-search "GARCH structural breaks"   # ranked notes: path + heading + snippet
```

Options: `--vault <path>`, `--k <n>`, `--reindex` (force rebuild).

## Development

```bash
uv run pytest
```

Embedding-dependent tests skip without `VOYAGE_API_KEY`; chunker tests are pure
and always run.
