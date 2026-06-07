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


def _emit(sec: _Section, note_path: str, heading_path: list[str], chunks: list[Chunk]):
    # Minimal one-chunk-per-section emit (size policy added in Task 3). Recurses so a
    # leading H1 title does not swallow its H2 siblings into one chunk.
    path = heading_path + ([sec.heading] if sec.heading else [])
    if sec.children:
        lead = sec.body()
        if lead.strip():
            chunks.append(Chunk(note_path, _breadcrumb(note_path, path),
                                len(chunks), lead.strip()))
        for child in sec.children:
            _emit(child, note_path, path, chunks)
        return
    full = sec.full_text()
    if full.strip():
        chunks.append(Chunk(note_path, _breadcrumb(note_path, path),
                            len(chunks), full.strip()))


def chunk_note(note_path: str, text: str, cfg) -> list[Chunk]:
    root = parse_tree(text)
    chunks: list[Chunk] = []
    preamble = root.body()
    if preamble.strip():
        chunks.append(Chunk(note_path, _breadcrumb(note_path, []),
                            len(chunks), preamble.strip()))
    for sec in root.children:
        _emit(sec, note_path, [], chunks)
    return chunks
