# Iteration 2 — Hybrid Retrieval (BM25 + dense) + Incremental Reindex

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps are committable per task.

## Goal

1. **Fix rare-exact-token recall** — acronyms / tickers (`KOSDAQ150`, `CET1`, `GARCH`) that
   pure dense cosine blurs should return their exact note, by adding a BM25 keyword signal
   and merging it with the existing vectors.
2. **Make reindex cheap** — re-embed only changed notes instead of rebuilding the whole
   vault each run, reusing the `note_hash` already stored in iteration 1.

## Features

| # | Feature | User-facing value | Task |
|---|---------|-------------------|------|
| 1 | BM25 full-text index (LanceDB native FTS) over body `text` | keyword/exact-token matching | 2 |
| 2 | Hybrid dense⊕BM25 via RRF rerank; `--mode vector\|fts\|hybrid` (default hybrid; `fts` offline) | acronym queries land; offline keyword search | 2 |
| 3 | Incremental `--reindex` via `note_hash` dedupe (new/changed embed, deleted dropped); `--rebuild` forces full | fast re-runs; explicit full rebuild when wanted | 3–4 |
| 4 | `--status` read-only drift report (added / changed / deleted vs index) | see if the index is stale without embedding | 4 |
| 5 | Synthetic acronym fixture (`KOSDAQ150`, `CET1`) | deterministic proof FTS finds what dense misses | 5 |

## Success criteria

- A keyword query for a rare token (`KOSDAQ150`) returns the note that dense-only ranked low/missed.
- Default `vault-search "q"` runs hybrid and stays at least as relevant as iter-1 dense on normal queries.
- `--mode fts "<token>"` works with no `VOYAGE_API_KEY` (fully offline).
- `--reindex` with no edits → **0 chunks embedded**; editing one note → only that note re-embeds.
- `--status` reports `IN SYNC` when matched, and the exact added/changed/deleted set when not.
- All deterministic tests pass without a key; key-gated reindex/e2e tests skip cleanly.

## Context

Iteration 1 shipped a dense-only `vault-search` CLI. Its acceptance run exposed the
weakness the roadmap predicted: **rare exact tokens** (acronyms, tickers — `GARCH`,
`KOSDAQ150`, `CET1`) blur under pure cosine and return topically-adjacent chunks instead
of the exact note. Iteration 2 adds a **BM25 keyword index** alongside the existing
vectors and **merges** the two, so exact-token queries land. It also makes `--reindex`
**incremental** (re-embed only changed notes via the `note_hash` already stored in iter 1),
and adds a read-only `--status` drift check (prototyped ad-hoc during iter 1).

No new data is required: BM25 is computed by LanceDB (native Tantivy FTS) over the `text`
column already in the index. No locked decision from the source design changes.

**Confirmed choices:** `--reindex` = incremental, `--rebuild` = force full rebuild; FTS over
**body `text` only**; rare-token validation by a **synthetic fixture** (no real acronym notes
exist yet — live acronym validation deferred).

**Roadmap:** `docs/plans/01-semantic-search-iteration-roadmap.md` (Iteration 2; `--status`
folded in, iter 3 demoted to optional).

## Key API facts (lancedb 0.33.0, verified)

- BM25 index: `table.create_fts_index("text", replace=True)` (native FTS, BM25-ranked).
  **Not auto-updated on insert** → rebuild after every sync.
- FTS query (offline, no embedding): `table.search(q, query_type="fts", fts_columns=["text"]).limit(k)`.
- Hybrid with **our own Voyage vectors** (no embedding registry):
  `table.search(query_type="hybrid").vector(qv).text(qtext).rerank(RRFReranker()).limit(k)`.
  `LanceHybridQueryBuilder` exposes `.vector/.text/.rerank/.where/.limit`.
- Mutation for incremental: `table.delete("note_path IN (...)")`, `table.add(rows)`.
- Reranker: `from lancedb.rerankers import RRFReranker`.

## Files

- **Modify** `src/obsidian_librarian/config.py` — add `search_mode="hybrid"`, `fts_column="text"`, `rrf_k=60`.
- **Modify** `src/obsidian_librarian/index.py` — FTS creation, mode-aware `search`, incremental helpers (`has_table`, `indexed_note_hashes`, `delete_notes`, `add_chunks`, `rebuild_fts`).
- **Modify** `src/obsidian_librarian/cli.py` — `_full_build` + `_sync`; flags `--reindex` (sync), `--rebuild` (force), `--status` (read-only), `--mode`.
- **Add** `tests/fixtures/acronyms.md` — note containing a rare token (`KOSDAQ150`, `CET1`).
- **Modify** `tests/test_index.py`, `tests/test_cli.py` — FTS / hybrid / incremental / status tests.

Reuse from iter 1: `vault.iter_notes` (already yields `note_hash`), `chunker.chunk_note`,
`embed.EmbeddingClient`, `VectorIndex._rows`.

---

## Task 1: Config knobs

- Add `search_mode: str = "hybrid"`, `fts_column: str = "text"`, `rrf_k: int = 60`.
- Test: extend `tests/test_config.py` — assert `search_mode == "hybrid"`, `fts_column == "text"`.
- Commit: `feat: config knobs for hybrid search`.

## Task 2: FTS index + mode-aware search (index.py)

TDD with **fake vectors** (no API):

- **Tests first** (`tests/test_index.py`):
  - `test_fts_finds_rare_token`: build rows incl. text `"capital ratio CET1 KOSDAQ150 disclosure"` with a vector orthogonal to the query; `search(query_text="KOSDAQ150", mode="fts", k=3)` returns that row first.
  - `test_hybrid_returns_both_signals`: one row wins on vector, another on text; `search(query_vector=..., query_text=..., mode="hybrid")` includes both.
  - keep existing `test_search_returns_nearest_first` working as `mode="vector"`.
- **Implement:**
  - `build(...)` also calls `create_fts_index(cfg.fts_column, replace=True)` after `create_table`.
  - `search(self, query_vector=None, query_text=None, k=8, mode=None)`:
    - `mode = mode or cfg.search_mode`.
    - `vector`: existing cosine path (`.metric("cosine")`).
    - `fts`: `t.search(query_text, query_type="fts", fts_columns=[cfg.fts_column]).limit(k)`.
    - `hybrid`: `t.search(query_type="hybrid").vector(list(query_vector)).text(query_text).rerank(RRFReranker()).limit(k)`.
    - pop `vector` (and `_relevance_score`/`_distance` left as-is) from each result dict.
- Commit: `feat: BM25 FTS index + vector/fts/hybrid search modes`.

## Task 3: Incremental sync helpers (index.py)

TDD with fake vectors:

- **Tests first:**
  - `test_indexed_note_hashes`: build 2 notes → returns `{note_path: note_hash}`.
  - `test_incremental_replace`: build a.md+b.md; `delete_notes(["a.md"])` + `add_chunks(new a rows, {"a.md":"h1b"})`; assert a.md hash updated, b.md row untouched, FTS still queryable after `rebuild_fts()`.
- **Implement:**
  - `has_table()` → `cfg.table_name in self.db.table_names()`.
  - `indexed_note_hashes()` → read rows, build `{note_path: note_hash}` (one per note).
  - `delete_notes(paths)` → skip if empty; `t.delete("note_path IN (" + ",".join(quoted) + ")")` (single-quote-escape paths).
  - `add_chunks(chunks, vectors, note_hashes)` → `t.add(list(self._rows(...)))`.
  - `rebuild_fts()` → `t.create_fts_index(cfg.fts_column, replace=True)`.
- Commit: `feat: incremental index mutation + note-hash readback`.

## Task 4: CLI — incremental `--reindex`, `--rebuild`, `--status`, `--mode`

- **`_full_build(cfg, embedder)`** = iter-1 `_reindex` body, now via `VectorIndex.build` (creates FTS). Used by `--rebuild`, and as fallback when `not has_table()`.
- **`_sync(cfg, embedder)`** (incremental, the new `--reindex`):
  - `notes = list(iter_notes(cfg))`; `cur = {n.note_path: n.note_hash}`.
  - if `not idx.has_table()` → `return _full_build(...)`.
  - `indexed = idx.indexed_note_hashes()`.
  - `new`/`changed`/`deleted` by hash compare; `to_embed = new + changed`.
  - `idx.delete_notes(deleted + [n.note_path for n in changed])`.
  - chunk+embed only `to_embed`; `idx.add_chunks(...)`; `idx.rebuild_fts()` (always — builds FTS on first sync even with 0 re-embeds).
  - echo `f"Synced: {len(new)} new, {len(changed)} changed, {len(deleted)} deleted, {n_chunks} chunks embedded"`.
- **`_status(cfg)`** (read-only, **no embedding**): same diff, print added/changed/deleted or `IN SYNC`; error if no table.
- **Query path:** `mode` from `--mode` or `cfg.search_mode`. Embed query only when `mode in {vector, hybrid}` (so `--mode fts` is fully offline). Call `idx.search(query_vector=qv, query_text=query, k=k, mode=mode)`.
- **Flags:** `--reindex` (sync), `--rebuild` (force full), `--status`, `--mode [vector|fts|hybrid]`, plus existing `--vault/--k`.
- **Tests** (`tests/test_cli.py`):
  - `test_status_reports_drift` (no API): temp vault + build index via `VectorIndex` with fake vectors keyed to the notes' real hashes; `main(["--vault",v,"--status"])` → `IN SYNC`; edit a note → run again → `changed`.
  - `test_fts_query_is_offline` (no API): build a fake-vector index containing `KOSDAQ150`; `main(["--vault",v,"--mode","fts","KOSDAQ150"])` returns the note with no `VOYAGE_API_KEY` set.
  - `test_reindex_incremental_zero_reembed` (skip w/o key): reindex twice → 2nd echoes `0 chunks embedded`; edit one note → only it re-embeds.
- Commit: `feat: incremental reindex, --rebuild, --status, --mode in CLI`.

## Task 5: Acronym fixture + docs

- `tests/fixtures/acronyms.md`: a note whose body contains `KOSDAQ150`, `CET1` (used by Task 2/4 rare-token tests).
- README: document `--mode` (default hybrid; `fts` is offline), `--rebuild`, `--status`, and that BM25 needs no extra data.
- `tests/queries.txt`: add 2 acronym queries.
- Commit: `docs: hybrid search usage + acronym fixture`.

---

## Migration / behavior notes

- First iter-2 `--reindex` on the existing 33-chunk index: `has_table()` true, 0 hash changes → 0 re-embeds, but `rebuild_fts()` still runs, so the BM25 index gets created. Hybrid/fts become available with no embedding cost.
- `note_path` single-quote escaping in `delete_notes` (defensive; vault paths rarely contain quotes).
- Keep stored `text` body-only (display stays clean); FTS over `text`, dense still embeds breadcrumb+body (unchanged).

## Verification (end-to-end)

1. `env -u PYTHONPATH uv run pytest -v` → all pass; FTS/hybrid/incremental/status deterministic (no key); key-gated reindex/e2e skip without key.
2. `env -u PYTHONPATH uv run vault-search --reindex` → `0 chunks embedded` but FTS built.
3. `env -u PYTHONPATH uv run vault-search --mode fts "voyage-4-large"` → offline keyword hit.
4. `env -u PYTHONPATH uv run vault-search "LanceDB rationale"` (hybrid default) → relevant top-k.
5. `--status` → `IN SYNC`; edit a note → `changed`; `--reindex` → only that note re-embeds (`1 changed`).
6. Rare-token proof: a query for the fixture's `KOSDAQ150` ranks the fixture above a dense-only run (unit-level, deterministic).

## Out of scope (later iterations)

Git change-oracle sync (iter 3, now optional), MCP server (iter 4), synthesis rule (iter 5),
images (iter 6), Docker (iter 7). Merge weighting beyond RRF left as a future knob.
