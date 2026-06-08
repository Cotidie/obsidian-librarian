# Iteration 5 — Synthesis workflow rule (`search_vault`-before-create) (shipped 2026-06-08)

> Plan for iteration 5 of [`01-semantic-search-iteration-roadmap.md`](01-semantic-search-iteration-roadmap.md).
> Status: **shipped** — `AGENTS.md` Synthesis rule edited. Test guide:
> [`../testing/06-iteration-5-synthesis-rule.md`](../testing/06-iteration-5-synthesis-rule.md).

## Context

The iteration the engine was built for. Iters 1–4 made the vault searchable by meaning and
exposed `search_vault` to Claude Code (iter 4). This one feeds retrieval into synthesis: when
the Librarian files an Inbox memo, it first searches the vault for the memo's key concepts and
updates/links an existing note instead of duplicating — the project's headline goal.

No repo code. Only change is the vault prompt `knowledge-base/AGENTS.md`. The mechanism
(`search_vault`) exists; this changes *when/how the agent calls it*.

Two locked constraints:

- The new rule **replaces** the manual "Search `02-Questions` and `03-Knowledge`" step with a
  `search_vault` call — not a dual path. One fallback line only.
- Thin corpus is a known external risk, not a blocker (iter-4 feedback). Real dedup may find
  nothing to merge. So the acceptance test **seeds its own fixture** (two overlapping memos),
  provable today; corpus-strengthening tracked separately.

## The plan

Edit `knowledge-base/AGENTS.md`, section "Synthesis rule (update before create)" (lines
150–167). Replace **step 1** — *"Search `02-Questions` and `03-Knowledge`..."* — with:

1. Before creating any Question or Knowledge note, call **`search_vault`** (the
   `obsidian-librarian` MCP tool) on the memo's key concepts. Top hits = candidate notes to
   update.
   - _Fallback:_ if `search_vault` unavailable, manual scan of `02-Questions` / `03-Knowledge`.

Steps 2–5 (update-vs-create, source link, edit-on-refine/contradict, fix `[[links]]`) stay
unchanged. "Applies to Reviews too" note stays. Inbox-processing steps (~205–207) already say
"apply the Synthesis rule" → inherit this with no separate edit.

## Eight-field iteration spec

- **Goal:** retrieval-driven dedup-before-filing.
- **User-facing value:** during Inbox review the Librarian calls `search_vault` on a memo's key
  concepts and extends/links an existing note instead of spawning a duplicate.
- **Features:** `search_vault`-before-create trigger in `AGENTS.md` (replacing the folder scan).
- **Deliverables:** edited `knowledge-base/AGENTS.md`; test guide
  `docs/testing/06-iteration-5-synthesis-rule.md` (written at execution time).
- **Testable conditions:** a real Inbox review shows Claude calling `search_vault` before
  creating and merging on overlap. Thin live corpus → test seeds two related memos; the second
  must extend the first's note, not duplicate.
- **User test flow:** drop two overlapping memos in `00-Inbox`, ask for a review, confirm the
  second merges/links into the first's note.
- **Feedback to collect:** does it cut duplication? trigger at the right moments (not too
  aggressive / not skipped)? is `search_vault` recall good enough on the *real* vault, or must
  corpus-strengthening land first?
- **Risks:** prompt wording iterates from behavior; corpus gap is the main external risk —
  tracked separately, not blocking.

## Verification

1. Re-read the Synthesis section: step 1 names `search_vault`, steps 2–5 intact, fallback line
   present, Reviews note unchanged.
2. Seeded run: two overlapping memos → review → one note, extended/linked (no near-duplicate);
   transcript shows a `search_vault` call before the create decision.
3. Negative check: a memo with no overlap still yields a *new* note (no over-merge).

## Out of scope

Images (iter 6); Docker + retiring `obsidian-vault` (iter 7); eval-corpus strengthening
(parallel task). No repo code changes.

## Feedback from Iteration 5

_To fill after a real seeded Inbox review — duplication reduced? trigger timing right?
`search_vault` recall sufficient on the live vault, or does corpus-strengthening need to land
first?_
