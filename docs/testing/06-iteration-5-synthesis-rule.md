# Test guide — Iteration 5: Synthesis rule (`search_vault`-before-create)

A hands-on, step-by-step script for **testing this iteration as a user**. It pairs with the
plan in [`../plans/06-iteration-5-synthesis-rule.md`](../plans/06-iteration-5-synthesis-rule.md)
and exercises the one behaviour this iteration introduces.

This iteration ships **no repo code** — it changes the vault's prompt
(`knowledge-base/AGENTS.md`) so the Librarian searches the vault *by meaning* before filing
an Inbox memo, and extends an existing note instead of creating a duplicate.

## What this iteration introduced

| Feature | What to expect |
|---------|----------------|
| **`search_vault`-before-create** | Step 1 of the "Synthesis rule (update before create)" in `AGENTS.md` now calls the `search_vault` MCP tool on a memo's key concepts before creating any Question/Knowledge note. |
| **Replaces the manual folder scan** | The old "search `02-Questions` and `03-Knowledge` by hand" wording is gone, kept only as a one-line **fallback** for when the MCP tool isn't available. |
| **Inbox review inherits it** | The Inbox-processing steps already say "apply the Synthesis rule," so a normal review now dedupes by semantic search with no extra wording. |
| **Rides the `CLAUDE.md` symlink** | `CLAUDE.md` is a symlink to `AGENTS.md`, so the rule is active for any agent that reads either file. |

> **Key interaction (don't skip):** the `obsidian-librarian` MCP server **syncs on launch,
> not per query** (iteration 4). So `search_vault` only finds notes that were indexed *before
> the session started*. A note the Librarian creates mid-review is **not** searchable until
> the next launch. The test below is built around this: the "existing" note is seeded and
> indexed **before** you open the session.

## Before you start

- The `obsidian-librarian` MCP server is registered with Claude Code and shows **connected**
  (`claude mcp list`). If not, see `docs/testing/05-iteration-4-mcp-server.md` step 3.
- `VOYAGE_API_KEY` is available to the server (needed to embed the seeded note at launch).
- Your vault is writable and you're comfortable adding/removing a couple of throwaway notes
  in `00-Inbox` and `03-Knowledge`.
- Vault root used in examples: `/home/cotidie/repositories/cotidie/knowledge-base`.

---

## Step 1 — Confirm the rule is in place

Open `knowledge-base/AGENTS.md` and find **"Synthesis rule (update before create)"**.

**Expect:** step 1 reads (roughly):

> 1. Call **`search_vault`** (the `obsidian-librarian` MCP tool) on the memo's key concepts
>    to find an existing note on the same topic … If `search_vault` is unavailable, fall back
>    to a manual scan of `02-Questions` and `03-Knowledge`.

Steps 2–5 (update vs create, source link, edit-on-refine, fix `[[links]]`) are unchanged.

---

## Step 2 — Seed an existing note and index it (the dedup target)

Create a throwaway Knowledge note so there is something for `search_vault` to find. Substitute
your own topic if you like — just keep step-4's memo on the **same** topic.

`03-Knowledge/Research starts with problem definition.md`:

```markdown
# Research starts with problem definition

The quality of a research project is set at its starting point. A sharp, well-posed
problem definition determines whether the methodology can even be valid. Vague framing
produces work that cannot be judged complete.
```

Now index it so it's searchable **before** the session (the server syncs on launch, so this
must exist in the index first):

```bash
cd /home/cotidie/repositories/cotidie/obsidian-librarian
env -u PYTHONPATH uv run vault-search --reindex
```

**Sanity check** — confirm the seeded note is retrievable from the terminal:

```bash
env -u PYTHONPATH uv run vault-search "why is the starting point of research important"
```

**Expect:** the seeded note appears in the top hits. (If it doesn't, the dedup test can't
succeed — fix retrieval first.)

---

## Step 3 — Drop an overlapping memo in the Inbox

Add a new memo on the **same topic**, phrased differently (so this genuinely tests *semantic*
dedup, not string matching). Use the `YYYYMMDD-HHmm` filename convention.

`00-Inbox/20260608-2230.md`:

```markdown
어디서 연구를 시작하느냐가 결국 연구의 성패를 가른다. 문제 정의가 명확해야
방법론이 타당해질 수 있고, 연구가 완성될 수 있다. 출발점이 흐릿하면 평가조차 어렵다.
```

(Korean on purpose — it overlaps the English seeded note only by *meaning*, which is exactly
what `search_vault` should bridge.)

---

## Step 4 — Run a real Inbox review and watch the merge

Open a **fresh** Claude Code session (so the server runs its launch sync and picks up the
seeded note), and ask:

> "Review my Inbox."

**Expect — the dedup case:**
- The Librarian **calls `search_vault`** on the memo's concepts before deciding to create a
  note (you'll see the tool call in the transcript).
- It finds `Research starts with problem definition` and **extends/links that note** with the
  memo's fragment — it does **not** spawn a near-duplicate like "연구의 시작점" as a separate
  note.
- The processed memo is moved to `00-Inbox/Processed`.

**Verify:** `03-Knowledge/` still has **one** note on this topic, now enriched, with a source
link back to the memo.

---

## Step 5 — Negative check (don't over-merge)

Drop a memo on an **unrelated** topic with no existing note, e.g.:

`00-Inbox/20260608-2240.md`:

```markdown
오늘 점심으로 김치찌개를 먹었다. 다음엔 다른 식당을 시도해보자.
```

Run the review again.

**Expect:** `search_vault` returns nothing relevant, so the rule correctly falls through to
"create a new note" (or, for a trivial memo, the existing guidance to *not* turn every memo
into a permanent note). The point: the rule **doesn't force a merge** when there's no real
overlap.

---

## Step 6 — Fallback behaviour (optional)

Temporarily make the tool unavailable (e.g. run the review in a session where the
`obsidian-librarian` MCP server isn't registered).

**Expect:** the Librarian falls back to a **manual scan** of `02-Questions` / `03-Knowledge`
as the rule's fallback line states — it still tries to dedupe, just without semantic search.

---

## Clean up

Delete the throwaway notes/memos you created (`03-Knowledge/Research starts with problem
definition.md`, the two `00-Inbox` memos or their `Processed` copies) and re-run
`vault-search --reindex` so the index drops them.

---

## What to report back (feedback wanted)

- **Did dedup actually fire?** Did the Librarian call `search_vault` and merge into the
  seeded note instead of duplicating?
- **Trigger timing** — did it search at the right moment, or skip it / over-merge unrelated
  memos?
- **Recall on the real vault** — with your *actual* notes (not the seeded one), is
  `search_vault` finding the right existing notes, or does the thin-corpus gap (iter-4
  feedback) make dedup unreliable until the corpus grows?
- **Sync-on-launch friction** — did "a note created earlier this session isn't searchable
  until restart" bite during multi-memo reviews? Would a manual `resync` tool help?
- **Prompt wording** — is step 1 clear enough, or does it need examples / tighter phrasing?
