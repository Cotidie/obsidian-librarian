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
| 2 | Hybrid retrieval | acronym/rare-token queries work | engine |
| 3 | Incremental sync | always-fresh, fast re-runs | engine |
| 4 | `obsidian-librarian` MCP | Claude Code can query the vault | wrapper |
| 5 | Synthesis rule | Librarian dedupes-before-filing | workflow |
| 6 | Image describe-to-text | images become searchable | enrichment |
| 7 | Docker + retire old MCP | reproducible install, one search system | hardening |

Iterations 1–3 are detailed below; 4–7 are intentionally light and will be re-planned
from feedback.

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

## Iteration 2 — Hybrid retrieval (add BM25)

- **Goal:** Fix rare-exact-token recall (CET1, KOSDAQ150) that dense-only blurs; avoid re-embedding unchanged notes.
- **User-facing value:** Same CLI now nails acronym/ticker queries; re-runs skip unchanged notes so reindex is cheaper.
- **Features introduced:** LanceDB BM25 full-text index + merge with dense results (default RRF or weighted — pick one, expose a knob); per-note content-hash dedupe so `--reindex` re-embeds only changed notes (full-scan hash compare, not git yet).
- **Deliverables:** hybrid path in `vault-search`; content-hash stored per note; merge strategy documented.
- **Testable conditions:** a BM25 query (`KOSDAQ150`) surfaces a note that pure-vector missed; `--reindex` with no edits → 0 re-embeds; edit one note → only it re-embeds.
- **User test flow:** rerun iter-1 acronym queries, compare ranking vs iter 1; reindex twice, observe 2nd is near-instant.
- **Feedback to collect:** Is acronym recall solved? Does hybrid ever hurt good dense hits (merge weighting)? Reindex speed acceptable?
- **Risks / open decisions:** merge strategy choice — default reversible, tune from feedback.

## Iteration 3 — Incremental sync (git change-oracle)

- **Goal:** Make the index self-freshening and O(changed files) without manual `--reindex`.
- **User-facing value:** Just run `vault-search "q"` — it silently reconciles to current vault state first (handles auto-backup commits + uncommitted edits) and is fast even at 10K notes.
- **Features introduced:** sync-on-invoke: `git diff --name-status <last_indexed_sha> HEAD` + `git status --porcelain` → A/M embed, D drop, R rename-path-only → hash-confirm candidates → persist new `HEAD` **last**; `last_indexed_sha` in a LanceDB meta row, validated via `git cat-file -e`; full rebuild on first run / drift; mtime+size git-less fallback.
- **Deliverables:** `sync` module wired ahead of every search; meta table; `--reindex` demoted to force-rebuild.
- **Testable conditions:** edit+commit one note → only it re-embeds; rerun no-change → 0 embeds; `git mv` → `note_path` updated, no re-embed; delete → dropped; auto-backup commit → 0 embeds; unset sha → full rebuild; kill mid-sync → next run redoes with no gap (proves "write last").
- **User test flow:** make a few edits/commits, run search, confirm new content is findable without manual reindex.
- **Feedback to collect:** Is launch latency acceptable after a burst of edits? Any staleness surprises?
- **Risks / open decisions:** none affecting sequencing; last engine-only iteration.

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
- **Features introduced:** Librarian step at review time — write `image-name.md` companion (caption + OCR + tags, frontmatter `image_path:`), move binary to `98-Resources/images/`; indexing unchanged (companion `.md` rides the normal git/hash/sync flow). Add the step to `AGENTS.md`.
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
