# Iteration 3 — Auto sync-on-query (hash-based)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps are committable per task.

## Context

After iteration 2, the index is kept fresh **manually**: `--reindex` re-embeds only changed
notes (by `note_hash`), `--status` shows drift. The remaining gap is that a plain
`vault-search "q"` can return **stale** results if notes changed since the last reindex — the
user has to remember to reindex first.

Iteration 3 closes that: every query **auto-reconciles** the index to the current vault first
(re-embed changed/new, drop deleted), so the user never types `--reindex`. A `--no-sync` flag
opts out for a fast/offline query. **No git** — this reuses the iteration-2 content-hash scan
(the git change-oracle was explicitly discarded). It is a small, optional convenience layer on
top of machinery that already exists.

Confirmed choices: **auto-reconcile** (silently embed changed notes, not just warn), **on by
default** with `--no-sync` to disable.

**Roadmap:** `docs/plans/01-semantic-search-iteration-roadmap.md` (Iteration 3, hash-based).

## Design

All machinery exists in `src/obsidian_librarian/cli.py` — this is mostly wiring:

- Reuse `_classify(cfg)` → `(idx, has_table, new, changed, deleted)` (already drives `_sync`/`_status`).
- Reuse `_chunk_notes`, `_embed_chunks`, and `VectorIndex.{delete_notes, add_chunks, rebuild_fts}`.

New `_auto_sync(cfg)`:
- `not has_table` → return `None` (caller shows a friendly "run --reindex" error).
- no drift → return `{"reconciled": 0}` (cheap: a hash scan, no embedding).
- drift → `delete_notes(deleted + changed)`, embed+`add_chunks(new + changed)`, `rebuild_fts()`.
  **Construct `EmbeddingClient` only when there is something to embed** (deletion-only reconcile
  stays offline). Wrap the embed/apply in `try/except` so an unavailable key (e.g. `--mode fts`
  with no key) degrades to a **stderr warning + stale results** instead of crashing.
- All progress/notices go to **stderr** (`click.echo(..., err=True)`) — keeps stdout result-only,
  which also pre-pays for MCP stdout purity in iter 4.

Wire into `main()` query path (after the `--reindex`/`--rebuild`/`--status` branches):
1. If a query is present and `not has_table()` → `raise click.UsageError("No index yet. Run --reindex first.")`.
2. If `query and not no_sync and not (reindex or rebuild)` → run `_auto_sync`; on `reconciled > 0`
   echo `(auto-synced N change(s))` to stderr.
3. Then the existing embed-query + `search` + `_print_hits` path, unchanged.

New flag: `--no-sync` (is_flag). `--reindex`/`--rebuild` already reconcile, so they skip auto-sync.

No config or schema changes (`note_hash` already stored; no meta table, no git).

## Files

- **Modify** `src/obsidian_librarian/cli.py` — add `_auto_sync`, `--no-sync`, no-index guard, wire into `main`.
- **Modify** `tests/test_cli.py` — auto-sync tests (below).
- **Modify** `README.md` — note that queries auto-sync; document `--no-sync`; update the "no automatic sync yet" limitation.
- **Modify** `docs/plans/01-semantic-search-iteration-roadmap.md` — mark Iteration 3 DONE.

## Tasks

### Task 1 — `_auto_sync` + `--no-sync` + guard (TDD)
Deterministic tests (no key):
- `test_query_without_index_errors`: query against an empty index dir → `UsageError` "run --reindex".
- `test_auto_sync_drops_deleted_offline`: fake-build (zero vectors) a 2-note vault; delete one file;
  `--mode fts "<deleted content>"` (no `--no-sync`) → result no longer contains the deleted note
  (deletion path needs no embedding, so this runs offline).
- `test_no_sync_skips_reconcile`: monkeypatch `cli._auto_sync` to raise; `--no-sync --mode fts "x"`
  → exit 0 (skipped); without `--no-sync` the same monkeypatch would raise (proves it's wired).

Key-gated test (skip without `VOYAGE_API_KEY`):
- `test_auto_sync_reembeds_edit`: `--reindex` build a vault; rewrite a note to add a new token;
  plain query for that token (no `--reindex`) → the note is found; stderr shows the auto-sync notice.

Reuse the existing `_fake_build` helper in `tests/test_cli.py`.

### Task 2 — Docs
- README: queries auto-sync by default; `--no-sync` to skip; replace the "no automatic sync yet"
  limitation bullet. Add `--no-sync` to the options table.
- Roadmap: mark Iteration 3 **DONE** with a one-line "what shipped".

## Verification

1. `env -u PYTHONPATH uv run pytest -q` → all pass; auto-sync deletion/guard/no-sync deterministic; key-gated edit test runs on the tier-0 key.
2. Live: `vault-search --reindex` once; edit a note (add a phrase); `vault-search "<phrase>"`
   **without** `--reindex` → the edit is found, stderr prints `(auto-synced 1 change(s))`.
3. `vault-search --no-sync "<phrase>"` right after another edit → does **not** reconcile (stale), no embedding.
4. Fresh index dir + a query → friendly "No index yet. Run --reindex first."

## Out of scope

Git change-oracle (discarded). Per-query hash-scan cost at very large vaults is a future concern —
measure before optimizing; do not add git. MCP server is iteration 4.
