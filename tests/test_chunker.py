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
    p = tmp_path / "big.md"
    p.write_text(big)
    from obsidian_librarian.chunker import chunk_note
    from obsidian_librarian.config import Config
    chunks = chunk_note("big.md", big, Config())
    assert len(chunks) >= 2
    assert all(c.breadcrumb.endswith("Big") for c in chunks)
