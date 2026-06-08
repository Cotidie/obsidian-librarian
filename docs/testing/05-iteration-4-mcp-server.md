# Test guide — Iteration 4: `obsidian-librarian` MCP server

A hands-on, step-by-step script for **testing this iteration as a user**. It pairs with
the plan in [`../plans/05-iteration-4-mcp-server.md`](../plans/05-iteration-4-mcp-server.md)
and exercises every feature the iteration introduced.

## What this iteration introduced

| Feature | What to expect |
|---------|----------------|
| **Stdio MCP server** | The same hybrid engine runs as a Model Context Protocol server (`obsidian-librarian`) that Claude Code launches over stdio. |
| **`search_vault` tool** | One tool — `search_vault(query, k=8, mode="hybrid")` — returns ranked chunks as `{note_path, breadcrumb, snippet}`. Claude can call it mid-session. |
| **Sync on launch (not per query)** | The index reconciles to the vault **once when the server starts**, then serves every call without re-syncing. The first search after a burst of edits may pause; the rest are fast. |
| **`OBSIDIAN_LIBRARIAN_NO_SYNC=1`** | Skips the launch sync for a fast/offline start (serves the existing index as-is). |
| **stdout purity** | stdout is the JSON-RPC channel only. All logs — ours *and* `lancedb`/`voyageai`/`httpx` — go to **stderr**, so the protocol never gets corrupted. |
| **Graceful degradation** | If embedding fails at launch (e.g. Voyage outage), the server logs a warning and serves the existing/partial index instead of dying. |
| **Shared `service.py` engine** | The CLI and the MCP server call one engine. A CLI `vault-search` and a `search_vault` call return the same hits. |

## Before you start

- Python 3.13 + [uv](https://docs.astral.sh/uv/), `uv sync` already run (pulls in the `mcp` SDK).
- `.env` has a `VOYAGE_API_KEY` (needed to embed new/changed notes at launch; `fts` and
  no-sync paths run offline).
- A built index helps the first launch be fast — run `uv run vault-search --reindex` once if
  you haven't indexed lately.
- All commands assume the project root as the working directory. The repo's absolute path is
  used in registration; substitute yours if different:
  `/home/cotidie/repositories/cotidie/obsidian-librarian`.
- **If your shell leaks a ROS `PYTHONPATH`**, prefix every command with `env -u PYTHONPATH`.
  The examples omit it for brevity.

---

## Step 1 — Confirm the server starts and stays JSON-RPC-clean (no client needed)

This proves the launch path and stdout purity without any MCP tooling. Feed three JSON-RPC
lines on stdin and watch what comes back on stdout.

```bash
{
  printf '%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_vault","arguments":{"query":"KOSDAQ150","k":3,"mode":"fts"}}}'
  sleep 8
} | OBSIDIAN_LIBRARIAN_NO_SYNC=1 uv run obsidian-librarian 2>/tmp/mcp.err
```

**Expect:**
- Every line printed to your terminal (stdout) is valid JSON starting with `{"jsonrpc":"2.0"`.
- The `id:2` response carries real note hits (look for `note_path`, `breadcrumb`, `snippet`).
- All the human-readable noise (server INFO, sync notices) is in `/tmp/mcp.err`, **not** stdout.

> `mode:"fts"` keeps this step offline and fast. Drop `OBSIDIAN_LIBRARIAN_NO_SYNC=1` and use
> `"mode":"hybrid"` to also exercise the launch sync + Voyage embedding (slower; needs the key).

**Quick purity check** — pipe stdout through a JSON validator; it should print nothing:

```bash
... uv run obsidian-librarian 2>/dev/null \
  | grep -v '^[[:space:]]*$' \
  | python3 -c 'import sys,json; [json.loads(l) for l in sys]' && echo "stdout is pure JSON-RPC"
```

---

## Step 2 — Inspect the tool with the MCP Inspector (optional, visual)

The official Inspector gives you a UI to list tools and run them by hand:

```bash
npx @modelcontextprotocol/inspector \
  uv run --directory /home/cotidie/repositories/cotidie/obsidian-librarian obsidian-librarian
```

**Expect:** the Inspector connects, lists **`search_vault`** with its `query / k / mode`
schema. Run it with a query you know exists in your vault → you get ranked chunks back.

---

## Step 3 — Register the server with Claude Code (user scope)

`-s user` registers it across all your projects (the default is *local* = this project only).
Pass the key and vault path as env vars so the server needs no `.env` or specific working dir:

```bash
claude mcp add obsidian-librarian -s user \
  -e VOYAGE_API_KEY=voy-... \
  -e VAULT_PATH=/home/cotidie/repositories/cotidie/knowledge-base \
  -- uv run --directory /home/cotidie/repositories/cotidie/obsidian-librarian obsidian-librarian
```

Shorter form — install the entry point on PATH first, then drop `--directory`:

```bash
uv tool install --editable /home/cotidie/repositories/cotidie/obsidian-librarian
claude mcp add obsidian-librarian -s user \
  -e VOYAGE_API_KEY=voy-... \
  -e VAULT_PATH=/home/cotidie/repositories/cotidie/knowledge-base \
  -- obsidian-librarian
```

Env precedence is `-e` flag > project `.env` > built-in default; honored vars are
`VOYAGE_API_KEY`, `VAULT_PATH`, `VAULT_INDEX_PATH`.

**Expect:** `claude mcp list` shows `obsidian-librarian` with a connected/OK status, and it's
available from any project (user scope), not just this repo.

---

## Step 4 — Use it in a Claude Code session

Open a Claude Code session and ask something that should live in your vault, e.g.:

> "Search my vault for notes on GARCH structural breaks."

**Expect:**
- Claude calls `search_vault` and answers grounded in real notes (paths/breadcrumbs you recognize).
- The hits are comparable to what `uv run vault-search "GARCH structural breaks"` returns from the
  terminal — same engine, same results.

---

## Step 5 — Verify sync happens once per launch, not per query

In one session, ask Claude to search **two or three different topics** in a row.

**Expect:** only the **first** call may pause (launch sync already ran at startup); subsequent
calls are fast. There is no re-sync between calls — searching never triggers a re-embed. (If you
watch the server's stderr, you see a single sync notice at launch and none per query.)

To feel the contrast: edit/add a note in the vault **mid-session**, then search for it. It may
**not** appear until you restart the server (sync is on launch, by design). Restart the session →
the new note is found. This is the deliberate iteration-3 learning applied here.

---

## Step 6 — Confirm graceful, offline-friendly startup

Register or launch a second variant with the launch sync disabled and confirm it still serves:

```bash
OBSIDIAN_LIBRARIAN_NO_SYNC=1 uv run obsidian-librarian   # then drive it as in Step 1
```

**Expect:** the server starts immediately (no embedding, no API call) and answers `fts`/cached
queries. Equally, if `VOYAGE_API_KEY` is missing but an index already exists, the server should
log a warning and still serve rather than crash.

---

## What to report back (feedback wanted)

- **First-search latency** after a batch of edits — acceptable, or too long?
- **Tool-output shape** — are `note_path` + `breadcrumb` + `snippet` enough for Claude to ground
  answers, or do you want more/less per hit (full chunk text, scores, line ranges)?
- **Sync-on-launch staleness** — in a long session, did "edit a note, can't find it until
  restart" actually bite? Should there be a manual `resync` tool or a TTL?
- **Any protocol/stdout glitch** — a malformed response, a stray non-JSON line, a hang on launch.
- **Registration friction** — did `claude mcp add` + first use work cleanly on your machine?
