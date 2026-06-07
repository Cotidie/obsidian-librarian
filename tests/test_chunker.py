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
