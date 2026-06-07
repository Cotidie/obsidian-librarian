# obsidian-librarian

Semantic search and synthesis over an Obsidian vault. Embeds notes with
[Voyage](https://www.voyageai.com/) (`voyage-4-large`), stores vectors in an
embedded [LanceDB](https://lancedb.com/) table, and answers meaning-based
queries from the terminal — later wrapped as an `obsidian-librarian` MCP server
for Claude Code.

## Status

CLI-first, built in vertical iterations. **Iteration 1 (this code): dense
semantic search CLI.** See [`docs/plans/`](docs/plans/):

- [`01-semantic-search-iteration-roadmap.md`](docs/plans/01-semantic-search-iteration-roadmap.md) — the 7-iteration roadmap (dense search → hybrid → sync → MCP → synthesis rule → image describe-to-text → Docker).
- [`02-iteration-1-search-cli.md`](docs/plans/02-iteration-1-search-cli.md) — implementation plan for iteration 1.

## Setup

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env            # then put your key in it
```

`.env` (gitignored) is loaded automatically by the CLI and the test suite:

```
VOYAGE_API_KEY=...              # required
# VAULT_PATH=/home/cotidie/repositories/cotidie/knowledge-base  # optional; else the default
```

Environment variables, if exported, still work and take precedence.

## Usage

```bash
uv run vault-search --reindex                  # build the index once
uv run vault-search "GARCH structural breaks"  # query
uv run vault-search --k 5 "변동성 레짐 전환"
```

The index is stored at `~/.cache/obsidian-librarian/` (outside the vault, never
committed). Iteration 1 has no auto-sync: re-run `--reindex` after editing notes.

## Development

```bash
uv run pytest
```

Embedding/end-to-end tests skip without `VOYAGE_API_KEY`; chunker, index, and
vault-walk tests always run.

> **Note:** if your shell sources ROS (a leaked `PYTHONPATH`), prefix commands
> with `env -u PYTHONPATH` so the project venv is not polluted, e.g.
> `env -u PYTHONPATH uv run pytest`.
