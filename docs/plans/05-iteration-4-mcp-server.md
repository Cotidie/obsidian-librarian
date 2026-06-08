# Iteration 4 — `obsidian-librarian` MCP server (shipped 2026-06-08)

> Detailed plan note for iteration 4 of [`01-semantic-search-iteration-roadmap.md`](01-semantic-search-iteration-roadmap.md).

## Context

The hybrid engine (iterations 1–3) was validated only from the terminal. The project's headline
goal — the Librarian deduping-before-filing during synthesis (iter 5) — needs Claude Code to query
the live vault *in-session*. This iteration wraps the engine as a **stdio MCP server** exposing one
tool, `search_vault`, and registers it with Claude Code.

Two prior-feedback constraints shaped it:

- **Sync on launch, not per query** (iter-3 learning). An MCP session fires many `search_vault`
  calls; per-call sync (hash-scan + possible re-embed + FTS rebuild) is wasteful and risks surprise
  embeds mid-edit. The server reconciles **once at startup**, then serves.
- **stdout is the JSON-RPC channel.** Any stray write — ours or a `lancedb`/`voyageai` library line
  — corrupts the protocol. Iteration 3 only routed *our* echoes to stderr, so library logging was
  still open.

Confirmed decisions: extract a shared `service.py` engine (CLI + server share one path); MCP-only
scope (eval-corpus strengthening tracked separately); no git (hash-based sync); no Docker (iter 7);
keep the old `obsidian-vault` MCP in parallel (retired in iter 7). SDK: FastMCP
(`mcp.server.fastmcp.FastMCP`), decorator tools + `mcp.run(transport="stdio")`.

## What shipped

1. **`service.py` engine** (refactor) — `classify`, `sync`, `auto_sync`, `search`, `rebuild`,
   `has_index`, and `sync_on_launch` (one-shot session-start reconcile: full build if empty else
   incremental; logs to stderr; never raises; `OBSIDIAN_LIBRARIAN_NO_SYNC=1` skips). A shared
   `_apply_reconcile` removes the delete/embed/rebuild-FTS duplication. `cli.py` is now thin
   presentation over `service.*`. Behaviour-preserving: the 25 prior tests pass unchanged.
2. **`mcp_server.py`** — FastMCP server `obsidian-librarian`; tool
   `search_vault(query, k=8, mode="hybrid") -> list[{note_path, breadcrumb, snippet}]` over
   `service.search`. `run()` does `load_dotenv` → route logging to stderr → `sync_on_launch` under
   an **fd-level stdout→stderr redirect** (the one noisy phase) → `mcp.run(transport="stdio")`. Sync
   is wired in `run()`, never in the tool.
3. **Packaging** — `mcp` dependency; `[project.scripts]` `obsidian-librarian = "obsidian_librarian.mcp_server:run"`.

## Files

- **New** `src/obsidian_librarian/service.py`, `src/obsidian_librarian/mcp_server.py`.
- **Modify** `src/obsidian_librarian/cli.py` (thin over `service`), `pyproject.toml` (dep + script).
- **New** `tests/test_service.py`, `tests/test_mcp.py`; **Modify** `tests/test_cli.py` (monkeypatch targets → `service`).
- **Modify** `README.md` (MCP section + feature bullet), `docs/plans/01-…roadmap.md` (iter 4 DONE).

## Verification (all green)

1. `uv run pytest` → **37 passed** (25 preserved + 7 engine + 5 MCP). Deterministic: stdout-purity
   subprocess test, sync-once wiring, offline fts list/search; key-gated hybrid e2e on the tier-0 key.
2. **Live** against the real vault (raw JSON-RPC pipe, hybrid `search_vault`): 2 stdout lines, both
   valid JSON-RPC, real note hits; sync notice + server INFO logs on stderr only.
3. Registration:
   `claude mcp add obsidian-librarian -- uv run --directory <repo> obsidian-librarian`; or inspect
   with `npx @modelcontextprotocol/inspector uv run --directory <repo> obsidian-librarian`.

## Out of scope

Docker + retiring `obsidian-vault` (iter 7); synthesis rule (iter 5); images (iter 6);
eval-corpus strengthening (separate follow-up — the saturated 1.00 eval set, per iter-3 feedback).

## Feedback from Iteration 4

_To fill after the user tests it in a real Claude Code session — latency on first search after edits,
tool-output shape usefulness for Claude, any protocol/stdout issues, and whether sync-on-launch
staleness within a long session is felt._
