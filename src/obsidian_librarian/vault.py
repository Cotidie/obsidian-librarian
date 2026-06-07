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
