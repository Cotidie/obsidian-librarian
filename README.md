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

### 1. Build the index (once, and after editing notes)

```bash
uv run vault-search --reindex
# → Indexed 1234 chunks from /home/cotidie/repositories/cotidie/knowledge-base
```

`--reindex` walks every `*.md` in the vault (skipping templates, `.obsidian/`,
`.git/`), chunks each note by heading structure, embeds the chunks with Voyage,
and writes them to LanceDB. It is a full rebuild — there is no auto-sync in
iteration 1, so re-run it whenever notes change.

### 2. Search

```bash
uv run vault-search "GARCH structural breaks"
uv run vault-search --k 5 "변동성 레짐 전환"        # Korean / mixed queries work
uv run vault-search --reindex "regime shift"      # rebuild, then query in one go
```

Each result is the matching note path, its breadcrumb (`folder > title >
heading`), and a snippet:

```
98-Resources/notes/volatility.md  [98-Resources/notes > volatility > GARCH 구조적 변화]
    변동성 레짐 전환에 대한 메모. structural break 탐지.
```

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `QUERY` | — | The search text (positional). Omit only with `--reindex`. |
| `--reindex` | off | Rebuild the index from the vault before any query. |
| `--vault PATH` | `$VAULT_PATH` or the configured default | Vault to index/search. |
| `--k N` | `8` | Number of results to return. |

The index lives at `~/.cache/obsidian-librarian/` (outside the vault, never
committed). Delete that directory to force a clean rebuild.

## Development

```bash
uv run pytest
```

Embedding/end-to-end tests skip without `VOYAGE_API_KEY`; chunker, index, and
vault-walk tests always run.

> **Note:** if your shell sources ROS (a leaked `PYTHONPATH`), prefix commands
> with `env -u PYTHONPATH` so the project venv is not polluted, e.g.
> `env -u PYTHONPATH uv run pytest`.
