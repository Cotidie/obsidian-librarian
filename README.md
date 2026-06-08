# obsidian-librarian

Meaning-based search over an Obsidian vault, from the terminal. Ask in natural
language (or by keyword) and get back the most relevant notes — ranked by what
they *mean*, not just the words they contain. Built to later back an
`obsidian-librarian` MCP server for Claude Code.

> Design notes and the iteration roadmap live in [`docs/plans/`](docs/plans/).

## Features

- **Hybrid retrieval** — dense semantic vectors and BM25 keywords together, so both
  paraphrases and rare exact tokens (acronyms, tickers) land.
- **Heading-aware chunking** — notes are split by structure and carry a
  `folder > title > heading` breadcrumb for precise, readable hits.
- **Incremental indexing** — only changed notes are re-embedded, so keeping the index
  fresh is cheap.
- **MCP server** — the same engine runs as a stdio MCP server so Claude Code can
  `search_vault` your notes in-session (sync-on-launch).

## How it works

- **Indexing.** Each note is split into chunks by heading structure, embedded with
  [Voyage](https://www.voyageai.com/) (`voyage-4-large`), and stored in an embedded
  [LanceDB](https://lancedb.com/) table. The same chunks also feed a BM25 keyword index.
- **Search is hybrid.** A query runs through two retrievers at once — **dense vectors**
  (catch meaning and paraphrase) and **BM25 keywords** (catch rare exact tokens like
  acronyms or tickers) — and the two rankings are fused into one result list.
- **Reindexing is incremental.** The index remembers a content hash per note. A reindex
  re-embeds only the notes whose text actually changed and drops deleted ones, so routine
  updates are cheap. (It compares file contents, not git history.)

## Setup

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env            # then put your key in it
```

`.env` (gitignored) is loaded automatically by the CLI and tests:

```
VOYAGE_API_KEY=...              # required
# VAULT_PATH=/home/cotidie/repositories/cotidie/knowledge-base  # optional; else the default
```

Exported environment variables still work and take precedence.

## Usage

**Build the index** the first time (queries keep it fresh after that, see below):

```bash
uv run vault-search --reindex     # incremental: re-embeds only changed notes
uv run vault-search --rebuild     # force a full rebuild from scratch
```

**Search:**

```bash
uv run vault-search "GARCH structural breaks"     # hybrid (default)
uv run vault-search --k 5 "변동성 레짐 전환"          # Korean / mixed queries work
uv run vault-search --mode fts "KOSDAQ150"        # keyword-only; runs offline, no API key
```

Every query **auto-syncs first**: before searching, the index is reconciled to the
current vault (re-embed changed/new notes, drop deleted ones) using the same cheap
content-hash scan as `--reindex`, so you never have to remember to reindex after
editing. Unchanged notes cost nothing (only their bytes are hashed), and a reconcile
that only deletes notes needs no API key. Pass `--no-sync` to skip it for a faster
(possibly stale) query. Sync notices print to stderr; stdout stays results-only.

Each result is numbered and shows the note path, its breadcrumb
(`folder > title > heading`), and a snippet:

```
"GARCH" · hybrid · 2 results
────────────────────────────────────────────────────────────
1. 98-Resources/notes/volatility.md
   98-Resources/notes > volatility > GARCH 구조적 변화
   변동성 레짐 전환에 대한 메모. structural break 탐지.
```

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `QUERY` | — | Search text (positional). Omit only when reindexing. |
| `--mode` | `hybrid` | `vector` (meaning) \| `fts` (keywords, offline) \| `hybrid` (both). |
| `--k N` | `8` | Number of results. |
| `--reindex` | off | Incrementally update the index, then query if a QUERY is given. |
| `--rebuild` | off | Force a full rebuild. |
| `--status` | off | Show which notes drifted from the index (read-only, no embedding). |
| `--no-sync` | off | Skip the auto-sync a query runs by default (faster, may be stale). |
| `--vault PATH` | `$VAULT_PATH` or default | Vault to index/search. |

The index lives at `~/.cache/obsidian-librarian/`, outside the vault and never
committed. Delete that directory for a clean slate.

### Current limitations

- **Per-query sync cost grows with vault size** — auto-sync hashes every file on each
  query. Cheap at the current scale; `--no-sync` skips it if it ever bites.
- **Results can cluster** — several top hits may be different chunks of the same note.

## MCP server (Claude Code)

The same engine is exposed to Claude Code as a stdio MCP server so the Librarian can
search your vault mid-session. It serves one tool, **`search_vault(query, k, mode)`**,
returning ranked chunks (`note_path`, breadcrumb, snippet).

Register it (user scope):

```bash
claude mcp add obsidian-librarian -- \
  uv run --directory /home/cotidie/repositories/cotidie/obsidian-librarian obsidian-librarian
```

Then, in a session, ask Claude to search a topic — it calls `search_vault` against the
live vault.

- **Sync on launch.** The index is reconciled **once when the server starts** (not per
  query), so the first search after a burst of edits may take a moment; the rest are fast.
  Set `OBSIDIAN_LIBRARIAN_NO_SYNC=1` to skip the launch sync (fast/offline start).
- **`VOYAGE_API_KEY`** is read from the project `.env` (same as the CLI).
- **stdout is the JSON-RPC channel** — all logs (ours and `lancedb`/`voyageai`) go to
  stderr. Inspect with the MCP Inspector:
  `npx @modelcontextprotocol/inspector uv run --directory <repo> obsidian-librarian`.

## Development

```bash
uv run pytest
```

Embedding / end-to-end tests skip without `VOYAGE_API_KEY`; chunker, index, and
vault-walk tests always run.

> **Note:** if your shell sources ROS (a leaked `PYTHONPATH`), prefix commands with
> `env -u PYTHONPATH` so the project venv stays clean, e.g. `env -u PYTHONPATH uv run pytest`.
