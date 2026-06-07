---
type: plan
status: draft
created: 2026-06-08
topic: Adaptive iteration roadmap for the semantic search + synthesis service
sequencing: CLI-first; host-uv throughout; Docker last
source_plan: "[[semantic-search-and-synthesis]]"
related:
  - "[[semantic-search-and-synthesis]]"
  - "[[SETUP]]"
---

# Adaptive Iteration Roadmap — Semantic Search & Synthesis

## Context

Source plan [[semantic-search-and-synthesis]] is a fully-researched design (decisions
locked: voyage-4-large, LanceDB, hybrid vector+BM25, stdio MCP `obsidian-librarian`,
describe-to-text images, host-uv with optional Docker). But its 5 implementation phases
are **infrastructure-ordered** (indexer → sync → MCP → rule → CLI) — none is
independently usable until phase 3+.

This roadmap re-slices the same scope into **vertical iterations**, each shipping
something the user can run and judge. After each iteration the user tests it directly;
that feedback revises the remaining (deliberately under-specified) iterations. No locked
technical decision is changed.

**Confirmed sequencing:** CLI-first — validate retrieval in the easy-to-debug terminal
before wrapping as MCP (matches the source plan's own "engine before wrapper" test
order). Run host-side via `uv`/venv throughout; Docker only as a final hardening step.

How to use this roadmap: detail each iteration in its own numbered plan note
(`02-…`, `03-…`) only when it is reached, folding in feedback from the prior one.

## Roadmap overview

| # | Iteration | User-facing slice | Layer |
|---|-----------|-------------------|-------|
| 1 | Dense search CLI | `vault-search "q"` → ranked notes | engine |
| 1.5 | Ingest hygiene | results stop surfacing meta/agent files | ingest |
| 2 | Hybrid retrieval | acronym/rare-token queries work | engine |
| 3 | Auto sync-on-query *(optional)* | no manual `--reindex` (hash-scan, no git) | engine |
| 4 | `obsidian-librarian` MCP | Claude Code can query the vault | wrapper |
| 5 | Synthesis rule | Librarian dedupes-before-filing | workflow |
| 6 | Image describe-to-text | images become searchable | enrichment |
| 7 | Docker + retire old MCP | reproducible install, one search system | hardening |

Iterations 1–3 are detailed below; 4–7 are intentionally light and will be re-planned
from feedback.

---

## Feedback from Iteration 1 (2026-06-08)

Iteration 1 shipped (`vault-search` CLI: chunker → voyage-4-large → LanceDB → cosine).
Acceptance run = real reindex + a 10-query set over the live vault. What it taught us,
and how it revises the rest of the roadmap:

- **The vault is mostly meta, not knowledge.** Before scoping, agent-instruction files
  dominated the index (`AGENTS.md` + `CLAUDE.md` = 48 of 81 chunks, ~59%), and since
  `CLAUDE.md` is a symlink to `AGENTS.md` the same text was embedded twice. They polluted
  top-k (e.g. a Korean memo query surfaced `CLAUDE.md`). **→ New iteration 1.5 (ingest
  hygiene), done:** `ignore_globs` now excludes `CLAUDE.md`/`AGENTS.md`/`README.md`;
  reindex dropped 81→33 chunks and the polluted query cleaned up.
- **Rare-token weakness confirmed empirically.** `GARCH`, `TinyBERT`, acronyms returned
  plan-adjacent chunks, not exact hits. **→ Iteration 2 (hybrid BM25) ordering validated;
  no change.**
- **`note_hash` already enables cheap drift detection + incremental** without git (proved
  with an ad-hoc status check). **→ Fold a `--status`/stale-check into iter 2, and
  re-scope iter 3:** the git change-oracle becomes an *optional speed optimization*, not a
  correctness requirement. At current scale a full reindex is ~2.7s, so iter 3 is deferred
  until reindex latency actually hurts.
- **Relevance can't be fully judged yet** — the vault has no domain notes (no real GARCH /
  TinyBERT note exists to retrieve). The iter-1/2 acceptance gate leans on synthetic
  queries until the vault grows or a few domain notes are seeded.
- **Zero-chunk notes vanish silently** (`README.md` → 0 chunks). Minor robustness item for
  iter 2/3 (a note with no chunks should still be tracked, or reported).
- **Operational footguns cost real time:** a leaked ROS `PYTHONPATH` breaks `uv run`
  (prefix `env -u PYTHONPATH`), and Voyage rate limits required retry/backoff + token-budget
  batching (now on a paid tier; limits relaxed). Docker (iter 7) would pre-empt the
  PYTHONPATH issue — a small argument for not deferring it indefinitely.
- **For iter 4 (MCP): stdout purity must account for `lancedb`/`voyageai` logging**, not
  just our own prints.

Net: ordering holds (CLI → hybrid → sync → MCP → synthesis → image → Docker), with **1.5
prepended** and **iter 3 demoted to optional**.

## Feedback from Iteration 2 (2026-06-08)

Iteration 2 shipped: BM25 + dense hybrid (`--mode vector|fts|hybrid`, RRF merge), incremental
`--reindex` (content-hash), `--rebuild`, and `--status`. What it taught us:

- **Hybrid needed zero new data and zero tuning.** LanceDB ships native BM25 FTS and an
  `RRFReranker`; the default RRF merge worked first try, with our own Voyage query vectors via
  `.vector().text()` (no embedding-registry wiring). The `rrf_k` knob is exposed but untouched.
  **→ the iter-2 "merge-strategy" risk did not materialize.**
- **Incremental reindex already delivers the freshness/cost goal** that iteration 3 was created
  for: no-op `--reindex` = 0 embeds, full vault ~2–3s, `--status` reports drift — all via the
  content-hash scan, no git. **→ Iteration 3 re-scoped again, and the git change-oracle dropped
  entirely (decided 2026-06-08):** the hash scan is enough, so iteration 3's only remaining value is
  making sync *automatic* (run the hash-scan implicitly before each query so the user never types
  `--reindex`). No git path will be built. Heading/goal below updated accordingly.
- **The validation gap is now a recurring blocker (iter 1 *and* iter 2).** The real vault has no
  acronym/domain notes, so the headline rare-token win was proven only on a synthetic fixture and a
  throwaway test vault — never live. **→ Recommended near-term task: build an evaluation set** —
  seed a handful of representative notes (acronyms, domain terms, Korean) or a labelled
  query→expected-note set — so every future iteration has a *real* acceptance gate instead of a
  synthetic one. This is the single highest-leverage non-feature work right now.
- **Top-k can be dominated by one note's chunks** (a "LanceDB" query returned three chunks from the
  same plan note). **→ retrieval-quality follow-up:** optional note-level grouping / max-chunks-per-note
  diversification. Not blocking; fold into a later quality pass.
- **Operational notes for iter 4 (MCP):** FTS is not auto-updated on insert (we rebuild it after each
  sync — cheap now, revisit at scale), and CLI output needed real formatting work to be readable —
  reuse the structured hit shape (path / breadcrumb / snippet) for the MCP tool result.

Net: ordering still holds. Iteration 3 reframed (auto-sync, hash-based; git approach dropped). New standing
recommendation: **stand up an evaluation set before leaning harder on relevance claims.**

---

## Iteration 1 — Dense semantic search CLI

- **Goal:** Prove voyage-4-large + LanceDB return meaningfully relevant vault chunks; lock chunking shape.
- **User-facing value:** Run `vault-search "GARCH structural breaks"` in the terminal and get ranked note paths + heading + snippet. Real meaning-based search over the vault, today.
- **Features introduced:** markdown chunker (recursive heading split + breadcrumb embed); Voyage embed interface (`VOYAGE_API_KEY`); LanceDB writer; dense cosine search; thin CLI. One-shot bulk index persisted to disk (`~/.cache/`, outside the vault); refresh via explicit `--reindex` (no auto-sync yet).
- **Deliverables:** `chunker`, `embed`, `index` (LanceDB writer), `vault-search` CLI; `uv`/venv project; short README (setup + `VOYAGE_API_KEY`).
- **Testable conditions:** chunker on ~5 real notes → expected chunk count/breadcrumb/sizes incl. edge cases (1-line memo = 1 chunk, nested `###`, oversized-leaf split); vector dim asserted; cosine sanity `cos("GARCH structural break","variance regime shift") > cos(…,"lunch menu")`; index `.lance` files exist on disk.
- **User test flow:** export key → `vault-search --reindex` once → run the ~10-query fixed set (incl. Korean / KR-EN mixed) → eyeball top-k relevance.
- **Feedback to collect:** Is retrieval relevant? Chunk granularity too coarse/fine? Korean & mixed quality? Snippet/breadcrumb useful? CLI ergonomics, default `k`?
- **Risks / open decisions:** Full reindex each `--reindex` is fine at vault size; chunking params (200–500 tok target) are the most likely thing feedback revises — keep them config, not hardcoded.

## Iteration 1.5 — Ingest hygiene (DONE 2026-06-08)

- **Goal:** Stop indexing non-knowledge files so relevance feedback is trustworthy.
- **User-facing value:** Search results stop surfacing agent-instruction / meta files.
- **What shipped:** `ignore_globs` excludes `CLAUDE.md`, `AGENTS.md`, `README.md`
  (the `CLAUDE.md`→`AGENTS.md` symlink also caused duplicate chunks). Reindex went
  81→33 chunks; a previously polluted query stopped returning `CLAUDE.md`.
- **Open follow-ups:** treat zero-chunk notes explicitly (e.g. `README.md`); revisit the
  ignore list as the vault grows (other meta files, dotfolders).

## Iteration 2 — Hybrid retrieval (add BM25) (DONE 2026-06-08)

- **What shipped:** native LanceDB BM25 FTS + RRF hybrid (`--mode vector|fts|hybrid`, default hybrid; `fts` offline); incremental `--reindex` (content-hash, 0-embed no-ops), `--rebuild`, read-only `--status`; acronym fixture for deterministic rare-token proof; 19 tests. Validated on a synthetic fixture (no live acronym notes in the vault yet — see iter-2 feedback).
- **Goal:** Fix rare-exact-token recall (CET1, KOSDAQ150) that dense-only blurs; avoid re-embedding unchanged notes.
- **User-facing value:** Same CLI now nails acronym/ticker queries; re-runs skip unchanged notes so reindex is cheaper.
- **Features introduced:** LanceDB BM25 full-text index + merge with dense results (default RRF or weighted — pick one, expose a knob); per-note content-hash dedupe so `--reindex` re-embeds only changed notes (full-scan hash compare, not git yet).
- **Deliverables:** hybrid path in `vault-search`; content-hash stored per note; merge strategy documented; a read-only `--status` drift check (added/changed/deleted vs index) exploiting the already-stored `note_hash` (prototyped in iter 1).
- **Testable conditions:** a BM25 query (`KOSDAQ150`) surfaces a note that pure-vector missed; `--reindex` with no edits → 0 re-embeds; edit one note → only it re-embeds.
- **User test flow:** rerun iter-1 acronym queries, compare ranking vs iter 1; reindex twice, observe 2nd is near-instant.
- **Feedback to collect:** Is acronym recall solved? Does hybrid ever hurt good dense hits (merge weighting)? Reindex speed acceptable?
- **Risks / open decisions:** merge strategy choice — default reversible, tune from feedback.

## Iteration 3 — Auto sync-on-query (hash-based)

- **Scope (git approach discarded 2026-06-08):** the git change-oracle is **dropped** — the
  content-hash scan from iteration 2 is enough. This iteration's only job is to run that scan
  *automatically* before each query so the user never types `--reindex`. No git, no
  `last_indexed_sha`, no commit inspection. It is **optional / low priority**: a full reindex is
  ~2–3s at current scale, so manual `--reindex` already suffices day-to-day. **Do the evaluation
  set (iter-2 feedback) before this.**
- **Goal:** Make the index self-freshening without a manual `--reindex` step.
- **User-facing value:** Just run `vault-search "q"` — it reconciles the index to the current vault
  (re-embed changed, drop deleted) before searching.
- **Features introduced:** wrap the existing `_sync` (hash diff of `iter_notes` vs stored
  `note_hash`) to run before each query; a `--no-sync` escape hatch to skip it; `--reindex` /
  `--rebuild` stay for explicit control. Only file bytes are hashed for unchanged notes — no
  embedding cost unless content changed.
- **Deliverables:** auto-sync wired ahead of search in the CLI; `--no-sync` flag.
- **Testable conditions:** edit a note then query (no `--reindex`) → new content is found; no-change
  query → 0 re-embeds; delete a note → it stops appearing; `--no-sync` skips reconciliation.
- **User test flow:** edit a note, run a normal query, confirm the edit is reflected without reindexing.
- **Feedback to collect:** Is per-query latency acceptable after a burst of edits? At what vault size
  does hashing-every-file-per-query start to hurt?
- **Risks / open decisions:** per-query hash-scan cost at very large vaults — measure before
  optimizing; do **not** pre-build a git path (explicitly discarded).

## Iteration 4 — `obsidian-librarian` MCP server

- **Goal:** Expose the validated engine to Claude Code over stdio.
- **User-facing value:** In a Claude Code session, the Librarian can call `search_vault(query, k)` against the live vault (sync-on-launch). Run host-side via `uv` (no Docker yet).
- **Features introduced:** stdio MCP server `obsidian-librarian` wrapping sync + search; `search_vault` tool returning ranked chunks (`note_path`, breadcrumb, snippet); registration in `~/.claude.json`. **stdout purity** — all logs to stderr.
- **Deliverables:** MCP server entrypoint; Claude Code registration; MCP Inspector run notes.
- **Testable conditions:** Inspector lists `search_vault` and returns results; stdout contains only JSON-RPC (grep for non-JSON lines → none); identical query gives CLI-comparable results.
- **User test flow:** register, open a session, ask Claude to `search_vault` a known topic, confirm sensible hits.
- **Feedback to collect:** latency in-session; tool output shape useful for Claude; any protocol/stdout issues.
- **Risks / open decisions:** keep `obsidian-vault` (old keyword MCP) installed in parallel until iter 7.

## Iteration 5 — Synthesis workflow rule

- **Goal:** Realize the project's headline goal — retrieval-driven dedup.
- **User-facing value:** When the Librarian files/synthesizes an Inbox memo, it first `search_vault`s the memo's key concepts and updates/links existing notes instead of duplicating.
- **Features introduced:** extend the Synthesis rule in `AGENTS.md` (→ `CLAUDE.md` symlink) with the `search_vault`-before-create trigger.
- **Deliverables:** edited `AGENTS.md` Synthesis section.
- **Testable conditions:** run a real Inbox review; confirm Claude queries before creating, and merges into an existing note when overlap exists.
- **User test flow:** drop two related memos, ask for a review, verify the second extends the first's note rather than spawning a duplicate.
- **Feedback to collect:** Does the rule actually reduce duplication? Triggering at the right moments / too aggressively?
- **Risks / open decisions:** prompt wording likely iterated from observed behavior.

## Iteration 6 — Image describe-to-text

- **Goal:** Make image attachments searchable without a multimodal index.
- **User-facing value:** Searching a concept in an image (incl. Korean OCR text) surfaces the image via its companion note.
- **Features introduced:** Librarian step at review time — write `image-name.md` companion (caption + OCR + tags, frontmatter `image_path:`), move binary to `98-Resources/images/`; indexing unchanged (companion `.md` rides the normal hash/sync flow). Add the step to `AGENTS.md`.
- **Deliverables:** `AGENTS.md` image step; one worked example companion note.
- **Testable conditions:** a query matching an image's caption/OCR returns the companion note pointing at the image.
- **User test flow:** add an image to the inbox, run review, then search a phrase only present in the image.
- **Feedback to collect:** caption/OCR quality (esp. Korean); is concept-only search (not visual similarity) enough?
- **Risks / open decisions:** reserve `voyage-multimodal-3` + second index only if visual similarity is later needed.

## Iteration 7 — Docker packaging + retire `obsidian-vault`

- **Goal:** Reproducible, dependency-isolated install; converge on one search system.
- **User-facing value:** `docker run` MCP entry with no host Python deps; the old keyword MCP is gone.
- **Features introduced:** slim Docker image (vault `:ro`, index on named volume, host UID/GID, `safe.directory`, secrets at runtime); switch MCP registration to `docker run`; **remove `obsidian-vault` from `~/.claude.json`** only after `search_vault`'s BM25 half is validated and `mcp-obsidian` isn't used for writes/tag-management.
- **Deliverables:** `Dockerfile`; updated MCP registration; SETUP/README note.
- **Testable conditions:** sub-second container start; `:ro` blocks writes; index volume persists across `--rm` (2nd run skips re-embed); index not root-owned; old MCP removed and nothing breaks.
- **User test flow:** rebuild, register the docker command, run a session search; confirm old MCP gone.
- **Feedback to collect:** container-start latency tolerable? any UID/volume friction worth keeping host-uv instead?
- **Risks / open decisions:** Docker is explicitly optional in the source plan — may be skipped entirely if host-uv proves sufficient.
