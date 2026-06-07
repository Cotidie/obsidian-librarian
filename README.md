# obsidian-librarian

Semantic search and synthesis over an Obsidian vault. Embeds notes with
[Voyage](https://www.voyageai.com/) (`voyage-4-large`), stores vectors in an
embedded [LanceDB](https://lancedb.com/) table, and answers meaning-based
queries from the terminal — later wrapped as an `obsidian-librarian` MCP server
for Claude Code.

## Status

CLI-first, built in vertical iterations. **Through iteration 2: hybrid
(dense + BM25) search with incremental reindex.** See [`docs/plans/`](docs/plans/):

- [`01-semantic-search-iteration-roadmap.md`](docs/plans/01-semantic-search-iteration-roadmap.md) — the 7-iteration roadmap (dense search → hybrid → sync → MCP → synthesis rule → image describe-to-text → Docker).
- [`02-iteration-1-search-cli.md`](docs/plans/02-iteration-1-search-cli.md) — iteration 1 (dense search CLI).
- [`03-iteration-2-hybrid-retrieval.md`](docs/plans/03-iteration-2-hybrid-retrieval.md) — iteration 2 (BM25 + hybrid, incremental reindex).

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
`.git/`, and agent/meta files), chunks each note by heading structure, embeds the
chunks with Voyage, and writes them to LanceDB plus a BM25 full-text index.

It is **incremental**: it re-embeds only notes whose content changed (by hash),
drops deleted ones, and rebuilds the keyword index — so re-runs after a small edit
are cheap. Use `--rebuild` to force a full rebuild, and `--status` to see drift
(added/changed/deleted) without embedding anything.

```bash
uv run vault-search --status     # read-only: IN SYNC, or what drifted
uv run vault-search --reindex    # incremental sync
uv run vault-search --rebuild    # force full rebuild
```

### 2. Search

```bash
uv run vault-search "GARCH structural breaks"        # hybrid (default)
uv run vault-search --k 5 "변동성 레짐 전환"             # Korean / mixed queries work
uv run vault-search --mode fts "KOSDAQ150"           # keyword-only, runs offline (no API)
uv run vault-search --reindex "regime shift"         # sync, then query in one go
```

**Search modes** (`--mode`): `hybrid` (default) blends dense vector similarity with
BM25 keyword scoring via reciprocal-rank fusion — vectors catch meaning, BM25 catches
rare exact tokens (acronyms, tickers). `vector` is dense only; `fts` is BM25 only and
needs no Voyage key. BM25 requires **no extra data** — it is computed from the notes
already indexed.

Each result is the matching note path, its breadcrumb (`folder > title >
heading`), and a snippet:

```
98-Resources/notes/volatility.md  [98-Resources/notes > volatility > GARCH 구조적 변화]
    변동성 레짐 전환에 대한 메모. structural break 탐지.
```

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `QUERY` | — | The search text (positional). Omit only with `--reindex`/`--rebuild`/`--status`. |
| `--reindex` | off | Incrementally sync the index (embed only changed notes), then query if given. |
| `--rebuild` | off | Force a full rebuild of the index. |
| `--status` | off | Read-only drift report (added/changed/deleted vs index); no embedding. |
| `--mode` | `hybrid` | Search mode: `vector` \| `fts` \| `hybrid`. `fts` is offline. |
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
