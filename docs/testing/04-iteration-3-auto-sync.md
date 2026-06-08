# Test guide — Iteration 3: Auto sync-on-query

A hands-on, step-by-step script for **testing this iteration as a user**. It pairs with
the plan in [`../plans/04-iteration-3-auto-sync.md`](../plans/04-iteration-3-auto-sync.md)
and exercises every feature the iteration introduced.

## What this iteration introduced

| Feature | What to expect |
|---------|----------------|
| **Auto sync-on-query** | A plain `vault-search "q"` reconciles the index to the vault (re-embed new/changed, drop deleted) **before** searching — you never run `--reindex` after editing. |
| **`--no-sync`** | Skips the auto-sync for a faster (possibly stale) query. |
| **No-index guard** | Querying before any index exists fails with a friendly `No index yet. Run --reindex first.` |
| **Offline deletion reconcile** | Removing notes syncs with no API key (nothing to embed). |
| **Graceful degradation** | If embedding fails mid-sync, you get a stderr warning + stale results instead of a crash. |
| **stdout stays results-only** | All sync notices print to **stderr**; stdout is just the ranked hits. |

## Before you start

- Python 3.13 + [uv](https://docs.astral.sh/uv/), `uv sync` already run.
- `.env` has a `VOYAGE_API_KEY` (needed for embedding new/changed notes; deletion-only
  and `--mode fts` paths run offline).
- All commands below assume the project root as the working directory.
- **If your shell leaks a ROS `PYTHONPATH`**, prefix every command with `env -u PYTHONPATH`
  (e.g. `env -u PYTHONPATH uv run vault-search ...`). The examples omit it for brevity.

> **Tip — keep stdout and stderr visible separately.** The point of this iteration is that
> sync notices go to stderr and results to stdout. To see which is which, run a query as
> `uv run vault-search "q" 2>/tmp/err.txt` then `cat /tmp/err.txt` for the stderr stream.

---

## Step 0 — Build the index once

```bash
uv run vault-search --reindex
```

**Expect:** `Indexed N chunks ... (full build)` the first time, or
`Synced: 0 new, 0 changed, 0 deleted, 0 chunks embedded` if it was already current.

---

## Step 1 — A query auto-syncs a brand-new note (no `--reindex`)

Add a note with a unique phrase, then query for it **without** reindexing:

```bash
printf '## Probe\n\nzubzubzub unique autosync phrase.\n' > "$VAULT_PATH/00-Inbox/zzz-probe.md"
uv run vault-search "zubzubzub"
```

(If `VAULT_PATH` isn't exported, use your vault path or `--vault <path>`.)

**Expect:**
- The new note `00-Inbox/zzz-probe.md` is the **top hit**.
- On **stderr**: `(auto-synced 1 change(s))`.

✅ This is the headline feature: the edit is searchable with no manual reindex.

---

## Step 2 — A query auto-syncs an *edit* to an existing note

Append a new unique token to the same note and search for it:

```bash
printf '## Probe\n\nzubzubzub unique autosync phrase. newtoken9 added.\n' > "$VAULT_PATH/00-Inbox/zzz-probe.md"
uv run vault-search "newtoken9"
```

**Expect:** the note is found on the new token, with `(auto-synced 1 change(s))` on stderr.

---

## Step 3 — `--no-sync` skips reconciliation (stale, but fast/offline)

Edit again, then query with `--no-sync`:

```bash
printf '## Probe\n\nzubzubzub phrase. token-stalecheck here.\n' > "$VAULT_PATH/00-Inbox/zzz-probe.md"
uv run vault-search --no-sync "token-stalecheck" 2>/tmp/err.txt
cat /tmp/err.txt
```

**Expect:**
- **No** `(auto-synced ...)` line on stderr (the file is empty) — the index was not touched.
- The just-added `token-stalecheck` is **not** found (the index is intentionally stale).
- No embedding API call is made.

Re-run **without** `--no-sync` to confirm it then syncs and finds the token:

```bash
uv run vault-search "token-stalecheck"
```

---

## Step 4 — Deleting a note reconciles offline (no API key needed)

Remove the probe note and search for its content:

```bash
rm "$VAULT_PATH/00-Inbox/zzz-probe.md"
uv run vault-search --mode fts "zubzubzub"
```

**Expect:**
- The deleted note **no longer appears** in results.
- `(auto-synced 1 change(s))` on stderr — and it works even though `--mode fts` and a
  deletion-only reconcile never call the embedding API.

---

## Step 5 — No-index guard

Point at an empty index directory and query:

```bash
VAULT_INDEX_PATH=/tmp/empty-index-$$ uv run vault-search "anything"
```

**Expect:** a clean, non-crashing error:

```
Error: No index yet. Run --reindex first.
```

---

## Step 6 — Confirm a no-op query stays cheap

With the vault unchanged since Step 4's cleanup, run any query:

```bash
uv run vault-search "GARCH"
```

**Expect:** results print normally and there is **no** `(auto-synced ...)` notice — a
no-change query does a cheap hash scan and embeds nothing.

---

## Cleanup

If you left a probe note behind, delete it and re-sync:

```bash
rm -f "$VAULT_PATH/00-Inbox/zzz-probe.md"
uv run vault-search --reindex
```

---

## Automated tests

The same behaviours are covered deterministically (no API key) plus one key-gated test:

```bash
uv run pytest tests/test_cli.py -q
```

Relevant tests: `test_query_without_index_errors`, `test_auto_sync_drops_deleted_offline`,
`test_no_sync_skips_reconcile` (deterministic), and `test_auto_sync_reembeds_edit`
(skips without `VOYAGE_API_KEY`).

---

## Feedback to collect

- Is per-query latency acceptable after a burst of edits?
- At what vault size does hashing-every-file-per-query start to hurt? (If it bites,
  `--no-sync` is the escape hatch.)
- Is the auto-sync behaviour discoverable, or surprising? Should the stderr notice be
  louder/quieter?
