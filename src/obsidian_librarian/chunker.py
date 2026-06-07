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


def _unwrap_title(root: _Section) -> None:
    # A leading H1 is the note title (the filename already carries it in the breadcrumb),
    # so it is not a structural container: merge its body into the preamble and promote
    # its children to top level. Keeps "Section A" reachable in breadcrumbs.
    promoted = []
    for child in root.children:
        if child.level == 1:
            if child.body():
                root.lines.append(child.body())
            promoted.extend(child.children)
        else:
            promoted.append(child)
    root.children = promoted


def _breadcrumb(note_path: str, heading_path: list[str]) -> str:
    parts = []
    folder = _folder_from_path(note_path)
    if folder:
        parts.append(folder)
    parts.append(_title_from_path(note_path))
    parts.extend(heading_path)
    return " > ".join(parts)


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
    _unwrap_title(root)
    chunks: list[Chunk] = []
    preamble = root.body()
    if preamble.strip():
        chunks.append(Chunk(note_path, _breadcrumb(note_path, []),
                            len(chunks), preamble.strip()))
    for sec in root.children:
        _emit_section(sec, note_path, [], cfg, chunks)
    # reindex chunk_index after all emits (defensive)
    for i, c in enumerate(chunks):
        c.chunk_index = i
    return chunks
