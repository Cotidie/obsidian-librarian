# Iteration 1 — Semantic Search CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `vault-search "query"` CLI that returns vault notes ranked by meaning, proving voyage-4-large + LanceDB retrieve relevant chunks and locking the chunking shape.

**Architecture:** A standalone Python (uv) project that walks the vault's `*.md`, chunks each note by markdown heading structure (with a folder/title/heading breadcrumb embedded into each chunk), embeds chunks with Voyage, stores vectors + metadata in an embedded LanceDB table on disk, and answers queries by embedding the query and returning top-k by cosine. Index built one-shot via `--reindex`; queries read the persisted index. No sync, no BM25, no MCP yet (iterations 2–4).

**Tech Stack:** Python 3.13, uv, `voyageai`, `lancedb` (+ `pyarrow`), `click`, `numpy`, `pytest`.

**Source design (master, in vault):** `knowledge-base/98-Resources/plans/semantic-search-and-synthesis.md` · **Roadmap:** `docs/plans/01-semantic-search-iteration-roadmap.md` (this repo)

**Location:** `docs/plans/02-iteration-1-search-cli.md` in this repo, beside the roadmap.

---

## Context

This is iteration 1 of the roadmap: the smallest end-to-end slice the user can run and judge. Everything is deliberately one-shot and host-side so retrieval quality can be validated in the easiest-to-debug surface before it is wrapped in sync (iter 3) or MCP (iter 4). The chunker is the highest-feedback component — its parameters are config, never hardcoded, because iteration-1 feedback is expected to revise them.

## File Structure

New repo: `~/repositories/cotidie/obsidian-librarian/`

```
obsidian-librarian/
├── pyproject.toml                  # uv project; console_script: vault-search
├── README.md
├── src/obsidian_librarian/
│   ├── __init__.py
│   ├── config.py                   # defaults: vault path, index path, model, dim, chunk bounds, ignore globs
│   ├── chunker.py                  # markdown -> [Chunk]; heading tree + size-bounded recursive split + breadcrumb
│   ├── embed.py                    # EmbeddingClient: embed_documents / embed_query (Voyage)
│   ├── index.py                    # LanceDB build + search
│   ├── vault.py                    # iterate vault *.md -> (note_path, text, note_hash)
│   └── cli.py                      # vault-search: query | --reindex | --vault | --k
└── tests/
    ├── fixtures/                   # ~5 sample .md notes incl. Korean / KR-EN-mixed, tiny, deeply nested
    ├── test_chunker.py             # pure, no API/DB
    ├── test_embed.py               # integration; skips without VOYAGE_API_KEY
    ├── test_index.py               # LanceDB insert/count/search/delete
    └── test_cli.py                 # end-to-end; skips without VOYAGE_API_KEY
```

Responsibility split: `chunker` is pure text→chunks (fast unit tests, no I/O). `embed` is the only thing that talks to Voyage, behind a thin interface so the provider can be swapped (per source plan) and so it can be faked in tests. `index` is the only thing that talks to LanceDB. `vault` is filesystem walking. `cli` wires them. This keeps each silent-failure landmine (chunking, embedding, storage) independently testable.

## Data model

`Chunk` (chunker output, in-memory): `note_path: str` (vault-relative), `breadcrumb: str`, `chunk_index: int`, `text: str` (body only, breadcrumb NOT prepended).

LanceDB row (one per chunk): `vector: list[float]` (dim from config), `note_path`, `breadcrumb`, `chunk_index`, `text`, `note_hash` (sha256 of the source file; unused for dedupe in iter 1 but stored now so iter 2 needs no migration).

**Embedded text** = `f"{breadcrumb}\n\n{text}"` — the breadcrumb is concatenated only at embed time (Retrieval design: "Embed the breadcrumb with the body"), so the stored `text` stays clean for display while the vector still carries hierarchy context.

---

## Task 1: Project scaffold + config

**Files:**
- Create: `~/repositories/cotidie/obsidian-librarian/pyproject.toml`
- Create: `src/obsidian_librarian/__init__.py`
- Create: `src/obsidian_librarian/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Initialize the uv project and add deps**

```bash
cd ~/repositories/cotidie/obsidian-librarian   # dir already exists (docs/plans present)
uv init --package --python 3.13                 # init in place, not `uv init <name>`
uv add voyageai lancedb pyarrow click numpy
uv add --dev pytest
git init && printf '.venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n' > .gitignore
```

- [ ] **Step 2: Write the failing test for config defaults**

```python
# tests/test_config.py
from obsidian_librarian.config import Config

def test_defaults_present():
    c = Config()
    assert c.model == "voyage-4-large"
    assert c.embed_dim == 1024
    assert c.chunk_max_tokens >= c.chunk_min_tokens > 0
    assert c.vault_path.endswith("knowledge-base")
    assert "lancedb" in c.index_path
    assert "templates" in " ".join(c.ignore_globs)
```

- [ ] **Step 3: Run it, expect failure**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: obsidian_librarian.config`

- [ ] **Step 4: Implement config**

```python
# src/obsidian_librarian/config.py
import os
from dataclasses import dataclass, field

DEFAULT_VAULT = "/home/cotidie/repositories/cotidie/knowledge-base"
DEFAULT_INDEX = os.path.expanduser("~/.cache/obsidian-librarian/lancedb")

@dataclass
class Config:
    vault_path: str = field(default_factory=lambda: os.environ.get("VAULT_PATH", DEFAULT_VAULT))
    index_path: str = field(default_factory=lambda: os.environ.get("VAULT_INDEX_PATH", DEFAULT_INDEX))
    table_name: str = "chunks"
    model: str = "voyage-4-large"
    embed_dim: int = 1024            # Matryoshka; half of 2048, near-full quality, smaller index
    chunk_min_tokens: int = 80       # below this, merge with siblings / keep whole note
    chunk_max_tokens: int = 500      # above this, descend a heading level or paragraph-split
    overlap_sentences: int = 1       # overlap when paragraph-splitting an oversized leaf
    ignore_globs: tuple = ("98-Resources/templates/*", ".obsidian/*", ".git/*")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: scaffold obsidian-librarian uv project + config defaults"
```

---

## Task 2: Chunker — heading tree + breadcrumb

**Files:**
- Create: `src/obsidian_librarian/chunker.py`
- Create: `tests/fixtures/` sample notes
- Test: `tests/test_chunker.py`

- [ ] **Step 1: Create fixture notes**

Create `tests/fixtures/nested.md`:

```markdown
# Title Ignored In Body

Preamble text under no heading.

## Section A

Body of A.

### Sub A1

Body of A1 with enough words to be its own thing when A overflows the limit.

## Section B

Body of B.
```

Create `tests/fixtures/tiny.md`:

```markdown
Just one line, no headings.
```

Create `tests/fixtures/korean.md`:

```markdown
## GARCH 구조적 변화

변동성 레짐 전환에 대한 메모. structural break 탐지.
```

- [ ] **Step 2: Write the failing breadcrumb/parse test**

```python
# tests/test_chunker.py
from pathlib import Path
from obsidian_librarian.chunker import chunk_note
from obsidian_librarian.config import Config

FIX = Path(__file__).parent / "fixtures"

def _chunks(name):
    text = (FIX / name).read_text()
    return chunk_note(note_path=name, text=text, cfg=Config())

def test_breadcrumb_includes_folder_title_heading():
    chunks = _chunks("nested.md")
    a = [c for c in chunks if "Section A" in c.breadcrumb][0]
    # breadcrumb is "folder > title > heading-path"; folder empty here, title from filename
    assert "nested" in a.breadcrumb
    assert "Section A" in a.breadcrumb

def test_every_chunk_has_path_and_monotonic_index():
    chunks = _chunks("nested.md")
    assert all(c.note_path == "nested.md" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
```

- [ ] **Step 3: Run it, expect failure**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: FAIL — `ModuleNotFoundError: obsidian_librarian.chunker`

- [ ] **Step 4: Implement the heading parser + breadcrumb (size split added in Task 3)**

```python
# src/obsidian_librarian/chunker.py
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

@dataclass
class Chunk:
    note_path: str
    breadcrumb: str
    chunk_index: int
    text: str

@dataclass
class _Section:
    level: int
    heading: str            # "" for the root/preamble
    lines: list = field(default_factory=list)   # body lines directly under this heading
    children: list = field(default_factory=list)

    def body(self) -> str:
        return "\n".join(self.lines).strip()

    def full_text(self) -> str:
        parts = []
        if self.heading:
            parts.append("#" * self.level + " " + self.heading)
        if self.body():
            parts.append(self.body())
        for c in self.children:
            parts.append(c.full_text())
        return "\n\n".join(p for p in parts if p)

def estimate_tokens(text: str) -> int:
    # Heuristic ~4 chars/token. Good enough for size bounds; configurable consumers
    # only need relative sizing, not exact Voyage tokenization.
    return max(1, len(text) // 4)

def _title_from_path(note_path: str) -> str:
    return PurePosixPath(note_path).stem

def _folder_from_path(note_path: str) -> str:
    parent = str(PurePosixPath(note_path).parent)
    return "" if parent == "." else parent

def parse_tree(text: str) -> _Section:
    root = _Section(level=0, heading="")
    stack = [root]
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            sec = _Section(level=level, heading=m.group(2))
            while stack and stack[-1].level >= level:
                stack.pop()
            (stack[-1] if stack else root).children.append(sec)
            stack.append(sec)
        else:
            stack[-1].lines.append(line)
    return root

def _breadcrumb(note_path: str, heading_path: list[str]) -> str:
    parts = []
    folder = _folder_from_path(note_path)
    if folder:
        parts.append(folder)
    parts.append(_title_from_path(note_path))
    parts.extend(heading_path)
    return " > ".join(parts)
```

For now add a minimal `chunk_note` that emits one chunk per top-level section (Task 3 replaces the splitting policy):

```python
def chunk_note(note_path: str, text: str, cfg) -> list[Chunk]:
    root = parse_tree(text)
    chunks: list[Chunk] = []
    def emit(text_body: str, heading_path: list[str]):
        if not text_body.strip():
            return
        chunks.append(Chunk(note_path, _breadcrumb(note_path, heading_path),
                            len(chunks), text_body.strip()))
    # preamble (root body) joins the title-level chunk
    preamble = root.body()
    if preamble and not root.children:
        emit(preamble, [])
    elif preamble:
        emit(preamble, [])
    for sec in root.children:
        emit(sec.full_text(), [sec.heading])
    return chunks
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: markdown heading-tree parser + breadcrumb chunking"
```

---

## Task 3: Chunker — size-bounded recursive split + edge cases

**Files:**
- Modify: `src/obsidian_librarian/chunker.py` (replace `chunk_note`)
- Test: `tests/test_chunker.py` (add cases)

- [ ] **Step 1: Write failing tests for the size policy**

```python
# append to tests/test_chunker.py
def test_tiny_note_is_single_chunk():
    chunks = _chunks("tiny.md")
    assert len(chunks) == 1
    assert "one line" in chunks[0].text

def test_small_section_keeps_subheadings_together():
    # nested.md Section A + Sub A1 are small combined -> one chunk, not split
    chunks = _chunks("nested.md")
    a_chunks = [c for c in chunks if c.breadcrumb.endswith("Section A")
                or "Sub A1" in c.breadcrumb]
    assert len(a_chunks) == 1
    assert "Sub A1" in a_chunks[0].text

def test_oversized_leaf_is_paragraph_split(tmp_path):
    big = "## Big\n\n" + "\n\n".join(f"Sentence {i}. " * 30 for i in range(8))
    p = tmp_path / "big.md"; p.write_text(big)
    from obsidian_librarian.chunker import chunk_note
    from obsidian_librarian.config import Config
    chunks = chunk_note("big.md", big, Config())
    assert len(chunks) >= 2
    assert all(c.breadcrumb.endswith("Big") for c in chunks)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: FAIL — `test_small_section_keeps_subheadings_together` / `test_oversized_leaf_is_paragraph_split`

- [ ] **Step 3: Replace `chunk_note` with the recursive size-bounded policy**

```python
# src/obsidian_librarian/chunker.py  (replace chunk_note and add helpers)
def _paragraph_split(body: str, cfg) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    out, cur = [], ""
    for p in paras:
        candidate = (cur + "\n\n" + p).strip() if cur else p
        if cur and estimate_tokens(candidate) > cfg.chunk_max_tokens:
            out.append(cur)
            # sentence overlap from the tail of the previous chunk
            sents = re.split(r"(?<=[.!?。])\s+", cur)
            tail = " ".join(sents[-cfg.overlap_sentences:]) if cfg.overlap_sentences else ""
            cur = (tail + "\n\n" + p).strip() if tail else p
        else:
            cur = candidate
    if cur:
        out.append(cur)
    return out or [body.strip()]

def _emit_section(sec: _Section, note_path: str, heading_path: list[str],
                  cfg, chunks: list[Chunk]):
    path = heading_path + ([sec.heading] if sec.heading else [])
    full = sec.full_text()
    if estimate_tokens(full) <= cfg.chunk_max_tokens:
        if full.strip():
            chunks.append(Chunk(note_path, _breadcrumb(note_path, path),
                                len(chunks), full.strip()))
        return
    # too big: if it has children, recurse; the section's own body rides with the first child
    if sec.children:
        lead = sec.body()
        if lead.strip():
            chunks.append(Chunk(note_path, _breadcrumb(note_path, path),
                                len(chunks), lead.strip()))
        for child in sec.children:
            _emit_section(child, note_path, path, cfg, chunks)
        return
    # oversized leaf: paragraph-split the body (heading stays in breadcrumb)
    for piece in _paragraph_split(sec.body(), cfg):
        chunks.append(Chunk(note_path, _breadcrumb(note_path, path),
                            len(chunks), piece))

def chunk_note(note_path: str, text: str, cfg) -> list[Chunk]:
    root = parse_tree(text)
    chunks: list[Chunk] = []
    preamble = root.body()
    # whole-note-is-tiny: single chunk
    if estimate_tokens(text) <= cfg.chunk_max_tokens and root.children:
        body = text.strip()
        if body:
            chunks.append(Chunk(note_path, _breadcrumb(note_path, []), 0, body))
        return chunks
    if preamble.strip():
        chunks.append(Chunk(note_path, _breadcrumb(note_path, []),
                            len(chunks), preamble.strip()))
    for sec in root.children:
        _emit_section(sec, note_path, [], cfg, chunks)
    # reindex chunk_index after all emits (defensive)
    for i, c in enumerate(chunks):
        c.chunk_index = i
    return chunks
```

- [ ] **Step 4: Run all chunker tests**

Run: `uv run pytest tests/test_chunker.py -v`
Expected: PASS (all)

- [ ] **Step 5: Eyeball real vault notes (manual, no assertion)**

Run:
```bash
uv run python -c "
from obsidian_librarian.chunker import chunk_note
from obsidian_librarian.config import Config
import pathlib
p='/home/cotidie/repositories/cotidie/knowledge-base/98-Resources/plans/semantic-search-and-synthesis.md'
for c in chunk_note('plan.md', pathlib.Path(p).read_text(), Config()):
    print(c.chunk_index, repr(c.breadcrumb), len(c.text))
"
```
Expected: a handful of chunks, breadcrumbs follow `plan > <H2>`, sizes within ~80–500 token estimate. Sanity only.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: size-bounded recursive heading split with leaf paragraph overlap"
```

---

## Task 4: Embedding client (Voyage)

**Files:**
- Create: `src/obsidian_librarian/embed.py`
- Test: `tests/test_embed.py`

- [ ] **Step 1: Verify the live Voyage model id + dim before coding**

Read current Voyage embeddings docs (model availability may have shifted since the source plan). Confirm: exact model id for the intended "voyage-4-large" tier, that it accepts `input_type` document/query, supported `output_dimension` values (Matryoshka), and `output_dtype`. If the id differs, update `Config.model` / `Config.embed_dim` only — no other code changes. Use the context7 docs tool or the Voyage docs site.

- [ ] **Step 2: Write the failing embedding test (skips without key)**

```python
# tests/test_embed.py
import os, math, pytest
from obsidian_librarian.embed import EmbeddingClient
from obsidian_librarian.config import Config

pytestmark = pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"),
                                reason="needs VOYAGE_API_KEY")

def _cos(a, b):
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(y*y for y in b))
    return dot / (na * nb)

def test_dim_and_cosine_sanity():
    c = EmbeddingClient(Config())
    docs = c.embed_documents(["GARCH structural break in volatility",
                              "today's lunch menu was bibimbap"])
    assert len(docs[0]) == Config().embed_dim
    q = c.embed_query("variance regime shift")
    assert _cos(q, docs[0]) > _cos(q, docs[1])
```

- [ ] **Step 3: Run, expect failure (or skip if no key)**

Run: `uv run pytest tests/test_embed.py -v`
Expected: FAIL `ModuleNotFoundError` (with key) or SKIPPED (no key).

- [ ] **Step 4: Implement the client**

```python
# src/obsidian_librarian/embed.py
import voyageai

class EmbeddingClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = voyageai.Client()  # reads VOYAGE_API_KEY from env

    def _embed(self, texts, input_type):
        # Voyage caps batch size/tokens per call; chunk into batches of 128.
        out = []
        for i in range(0, len(texts), 128):
            batch = texts[i:i+128]
            r = self.client.embed(batch, model=self.cfg.model,
                                  input_type=input_type,
                                  output_dimension=self.cfg.embed_dim,
                                  output_dtype="float")
            out.extend(r.embeddings)
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]
```

Note: if Step 1 found that `output_dimension`/`output_dtype` kwargs differ for the live model, adjust here. Keep the `embed_documents`/`embed_query` signatures fixed — `index` and `cli` depend on them.

- [ ] **Step 5: Run test (with a real key) to verify it passes**

Run: `VOYAGE_API_KEY=... uv run pytest tests/test_embed.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: Voyage embedding client (document/query, batched)"
```

---

## Task 5: LanceDB index (build + search)

**Files:**
- Create: `src/obsidian_librarian/index.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write failing tests with fake vectors (no API)**

```python
# tests/test_index.py
from obsidian_librarian.index import VectorIndex
from obsidian_librarian.chunker import Chunk
from obsidian_librarian.config import Config

def _cfg(tmp_path):
    c = Config(); c.index_path = str(tmp_path / "db"); c.embed_dim = 4; return c

def _rows():
    chunks = [Chunk("a.md", "a > X", 0, "alpha"),
              Chunk("b.md", "b > Y", 0, "beta")]
    vecs = [[1.0, 0, 0, 0], [0, 1.0, 0, 0]]
    return chunks, vecs

def test_build_then_count(tmp_path):
    cfg = _cfg(tmp_path)
    idx = VectorIndex(cfg)
    chunks, vecs = _rows()
    idx.build(chunks, vecs, note_hashes={"a.md": "h1", "b.md": "h2"})
    assert idx.count() == 2

def test_search_returns_nearest_first(tmp_path):
    cfg = _cfg(tmp_path)
    idx = VectorIndex(cfg)
    chunks, vecs = _rows()
    idx.build(chunks, vecs, note_hashes={"a.md": "h1", "b.md": "h2"})
    hits = idx.search([0.9, 0.1, 0, 0], k=2)
    assert hits[0]["note_path"] == "a.md"
    assert {"note_path", "breadcrumb", "text", "chunk_index"} <= hits[0].keys()
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_index.py -v`
Expected: FAIL — `ModuleNotFoundError: obsidian_librarian.index`

- [ ] **Step 3: Implement the index**

```python
# src/obsidian_librarian/index.py
import os
import lancedb

class VectorIndex:
    def __init__(self, cfg):
        self.cfg = cfg
        os.makedirs(cfg.index_path, exist_ok=True)
        self.db = lancedb.connect(cfg.index_path)

    def _rows(self, chunks, vectors, note_hashes):
        for c, v in zip(chunks, vectors):
            yield {"vector": list(v), "note_path": c.note_path,
                   "breadcrumb": c.breadcrumb, "chunk_index": c.chunk_index,
                   "text": c.text, "note_hash": note_hashes.get(c.note_path, "")}

    def build(self, chunks, vectors, note_hashes):
        # one-shot: drop and recreate (iter 1 has no incremental path)
        self.db.drop_table(self.cfg.table_name, ignore_missing=True)
        data = list(self._rows(chunks, vectors, note_hashes))
        self.db.create_table(self.cfg.table_name, data=data)

    def _table(self):
        return self.db.open_table(self.cfg.table_name)

    def count(self) -> int:
        return self._table().count_rows()

    def search(self, query_vector, k: int = 8) -> list[dict]:
        res = (self._table().search(list(query_vector))
               .metric("cosine").limit(k).to_list())
        for r in res:
            r.pop("vector", None)
        return res
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_index.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: LanceDB vector index build + cosine search"
```

---

## Task 6: Vault walker + CLI wiring (end-to-end)

**Files:**
- Create: `src/obsidian_librarian/vault.py`
- Create: `src/obsidian_librarian/cli.py`
- Modify: `pyproject.toml` (console script)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing vault-walk test (pure)**

```python
# tests/test_cli.py
from obsidian_librarian.vault import iter_notes
from obsidian_librarian.config import Config

def test_iter_notes_skips_ignored(tmp_path):
    (tmp_path / "00-Inbox").mkdir()
    (tmp_path / "00-Inbox" / "memo.md").write_text("hello")
    (tmp_path / "98-Resources" / "templates").mkdir(parents=True)
    (tmp_path / "98-Resources" / "templates" / "T.md").write_text("<% tp %>")
    cfg = Config(); cfg.vault_path = str(tmp_path)
    paths = {n.note_path for n in iter_notes(cfg)}
    assert "00-Inbox/memo.md" in paths
    assert all("templates" not in p for p in paths)
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: obsidian_librarian.vault`

- [ ] **Step 3: Implement the vault walker**

```python
# src/obsidian_librarian/vault.py
import hashlib
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

@dataclass
class Note:
    note_path: str   # vault-relative, posix
    text: str
    note_hash: str

def _ignored(rel: str, cfg) -> bool:
    return any(fnmatch(rel, g) for g in cfg.ignore_globs)

def iter_notes(cfg):
    root = Path(cfg.vault_path)
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        if _ignored(rel, cfg):
            continue
        raw = p.read_bytes()
        yield Note(rel, raw.decode("utf-8", "replace"),
                   hashlib.sha256(raw).hexdigest())
```

- [ ] **Step 4: Run the walk test to verify it passes**

Run: `uv run pytest tests/test_cli.py::test_iter_notes_skips_ignored -v`
Expected: PASS

- [ ] **Step 5: Implement the CLI**

```python
# src/obsidian_librarian/cli.py
import click
from .config import Config
from .vault import iter_notes
from .chunker import chunk_note
from .embed import EmbeddingClient
from .index import VectorIndex

def _reindex(cfg) -> int:
    notes = list(iter_notes(cfg))
    all_chunks, hashes = [], {}
    for n in notes:
        hashes[n.note_path] = n.note_hash
        all_chunks.extend(chunk_note(n.note_path, n.text, cfg))
    embedder = EmbeddingClient(cfg)
    texts = [f"{c.breadcrumb}\n\n{c.text}" for c in all_chunks]
    vectors = embedder.embed_documents(texts)
    VectorIndex(cfg).build(all_chunks, vectors, hashes)
    return len(all_chunks)

@click.command()
@click.argument("query", required=False)
@click.option("--reindex", is_flag=True, help="Rebuild the index from the vault.")
@click.option("--vault", default=None, help="Vault path override.")
@click.option("--k", default=8, help="Number of results.")
def main(query, reindex, vault, k):
    cfg = Config()
    if vault:
        cfg.vault_path = vault
    if reindex:
        n = _reindex(cfg)
        click.echo(f"Indexed {n} chunks from {cfg.vault_path}")
        if not query:
            return
    if not query:
        raise click.UsageError("Provide a QUERY, or --reindex.")
    qv = EmbeddingClient(cfg).embed_query(query)
    hits = VectorIndex(cfg).search(qv, k=k)
    for h in hits:
        click.echo(f"{h['note_path']}  [{h['breadcrumb']}]")
        snippet = h["text"].replace("\n", " ")[:160]
        click.echo(f"    {snippet}")
```

- [ ] **Step 6: Register the console script**

In `pyproject.toml`, under `[project.scripts]`:

```toml
[project.scripts]
vault-search = "obsidian_librarian.cli:main"
```

- [ ] **Step 7: Write the end-to-end test (skips without key)**

```python
# append to tests/test_cli.py
import os, pytest
from click.testing import CliRunner
from obsidian_librarian.cli import main

@pytest.mark.skipif(not os.environ.get("VOYAGE_API_KEY"), reason="needs VOYAGE_API_KEY")
def test_end_to_end_reindex_and_query(tmp_path, monkeypatch):
    (tmp_path / "n.md").write_text("## GARCH\n\nstructural break in variance regime")
    monkeypatch.setenv("VAULT_INDEX_PATH", str(tmp_path / "db"))
    r = CliRunner().invoke(main, ["--vault", str(tmp_path), "--reindex",
                                  "regime shift variance"])
    assert r.exit_code == 0
    assert "n.md" in r.output
```

- [ ] **Step 8: Run the full suite**

Run: `VOYAGE_API_KEY=... uv run pytest -v`
Expected: PASS (embed/e2e run; chunker/index/vault always run)

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: vault walker + vault-search CLI (reindex + query) end-to-end"
```

---

## Task 7: README + manual validation harness

**Files:**
- Create: `README.md`
- Create: `tests/queries.txt` (the fixed ~10-query set incl. Korean / KR-EN-mixed)

- [ ] **Step 1: Write the fixed query set**

Create `tests/queries.txt` with ~10 real questions about the vault, e.g.:

```
GARCH structural breaks
변동성 레짐 전환
TinyBERT distillation experiments
adjusting to a new lab
semantic search design decisions
voyage embedding model choice
한국어 메모 검색 품질
```

- [ ] **Step 2: Write the README**

```markdown
# obsidian-librarian (iteration 1: search CLI)

Meaning-based search over the Obsidian vault.

## Setup
    uv sync
    export VOYAGE_API_KEY=...        # required
    export VAULT_PATH=/home/cotidie/repositories/cotidie/knowledge-base  # or rely on default

## Use
    uv run vault-search --reindex                 # build the index once
    uv run vault-search "GARCH structural breaks" # query
    uv run vault-search --k 5 "변동성 레짐 전환"

Index is stored at ~/.cache/obsidian-librarian/ (outside the vault; never committed).
Iteration 1 has no auto-sync: re-run --reindex after editing notes.
```

- [ ] **Step 3: Run the manual validation (the only "works for me" test)**

```bash
export VOYAGE_API_KEY=...
uv run vault-search --reindex
while read -r q; do echo "=== $q ==="; uv run vault-search "$q"; done < tests/queries.txt
```
Expected: top results are judged relevant by eye for each query, including the Korean / mixed ones. This is the iteration's acceptance gate.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs: README + fixed validation query set"
```

---

## Self-Review (against the roadmap's iteration 1)

- **Features introduced** (chunker, embed interface, LanceDB writer, dense cosine search, thin CLI, one-shot persisted index, `--reindex`): Tasks 2–3, 4, 5, 5, 6, 6, 6. ✓
- **Deliverables** (chunker / embed / index modules, `vault-search` CLI, uv project, README): Tasks 1–7. ✓
- **Testable conditions:** chunker count/breadcrumb/sizes + edge cases (Task 2–3); vector dim assert + cosine sanity (Task 4); `.lance` files + insert/count/search (Task 5); end-to-end (Task 6). ✓
- **Chunk params are config, not hardcoded** (`Config.chunk_*`): Task 1. ✓ (the roadmap's named risk)
- **Index lives outside the vault** (`~/.cache/...`): Task 1 / 5. ✓
- **Feedback to collect** (relevance, granularity, Korean/mixed, ergonomics, k): exercised by Task 7. ✓
- Deferred correctly to later iterations: BM25 (iter 2), content-hash dedupe use (iter 2 — hash stored now), git sync (iter 3), MCP (iter 4), Docker (iter 7). `note_hash` is stored but unused, so iter 2 needs no schema migration.

## Verification (end-to-end)

1. `uv run pytest -v` with no key → chunker/index/vault tests pass, embed/e2e skip.
2. `VOYAGE_API_KEY=… uv run pytest -v` → all pass.
3. `uv run vault-search --reindex` then run `tests/queries.txt` → eyeball top-k relevance, especially Korean / mixed. This is the acceptance gate and the feedback the roadmap revises iteration 2 from.
