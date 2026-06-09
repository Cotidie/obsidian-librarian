<p align="center">
  <img src="docs/cover.png" alt="Obsidian Librarian" width="100%">
</p>

# Obsidian Librarian

Semantic search for your Obsidian vault, straight from Claude.

Obsidian Librarian turns your vault into a true second brain: ask a question in
plain language and get back the notes that actually answer it, ranked by what
they mean rather than the exact words you typed. A search for "volatility regime
change" will surface a note about "GARCH structural breaks" even if your wording
never appears in it.

The goal is a self-growing knowledge base. Because Claude can both search the
vault and write to it, your notes stop being a static archive: Claude finds what
you already know, fills the gaps, and links new notes back in, so the vault keeps
getting richer the more you use it.

## What it does

- **Finds notes by meaning.** Describe what you're looking for and it finds the
  closest matches, even when the wording differs.
- **Still catches exact terms.** Acronyms, tickers, and rare keywords (like
  `KOSDAQ150`) are matched precisely, so nothing slips through.
- **Works across languages.** Korean, English, and mixed queries all work.
- **Points you to the right spot.** Each result shows the note, the section it
  came from, and a short snippet, so you know why it matched.
- **Stays fresh cheaply.** After you edit notes, an update re-reads only what
  changed instead of redoing everything.

## Prerequisites

- **[Claude Code](https://claude.com/claude-code)** to run the MCP server.
- **[uv](https://docs.astral.sh/uv/)** and Python 3.13 to run the project.
- **A [Voyage API key](https://www.voyageai.com/)** for the embeddings that power
  meaning-based search.

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

## From the terminal

The same search also runs as a standalone command.

Build the index once, then refresh it whenever your notes change:

```bash
uv run vault-search --reindex     # update: re-reads only changed notes
uv run vault-search --rebuild     # start over from scratch
```

Search:

```bash
uv run vault-search "GARCH structural breaks"     # search by meaning (default)
uv run vault-search --k 5 "변동성 레짐 전환"          # Korean and mixed queries work
uv run vault-search --mode fts "KOSDAQ150"        # keyword-only, runs offline
```

Results look like this:

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
| `QUERY` | — | Search text. Omit only when refreshing the index. |
| `--mode` | `hybrid` | `vector` (meaning) \| `fts` (keywords, offline) \| `hybrid` (both). |
| `--k N` | `8` | Number of results. |
| `--reindex` | off | Refresh the index, then search if a query is given. |
| `--rebuild` | off | Rebuild the index from scratch. |
| `--status` | off | Show which notes have drifted from the index. |
| `--vault PATH` | default | Which vault to use. |

The index lives at `~/.cache/obsidian-librarian/`, outside your vault. Delete
that folder for a clean slate.

### Good to know

- **No auto-sync yet.** Run `--reindex` after editing notes (it's cheap).
- **Results can cluster.** Several top hits may come from the same note.

## Development

```bash
uv run pytest
```

Embedding tests skip without `VOYAGE_API_KEY`; the rest always run.

> If your shell sources ROS (a leaked `PYTHONPATH`), prefix commands with
> `env -u PYTHONPATH`, e.g. `env -u PYTHONPATH uv run pytest`.
