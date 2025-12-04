import sys
import types
from pathlib import Path

import pytest


# Fake MarkItDown used by bulk converter
class FakeResult:
    def __init__(self, markdown: str):
        self.markdown = markdown


class FakeMarkItDown:
    def __init__(self, enable_plugins: bool | None = None):
        self.enable_plugins = enable_plugins

    def convert_local(self, path: str):
        p = Path(path)
        return FakeResult(markdown=f"#{p.name}\n\nConverted from {p}")


@pytest.fixture(autouse=True)
def _patch_bulk_markitdown(monkeypatch):
    # Patch the MarkItDown class used inside bulk converter module
    import markitdown.bulk_converter._bulk as bc

    monkeypatch.setattr(bc, "MarkItDown", FakeMarkItDown)
    yield


def _make_tree(root: Path):
    (root / "a").mkdir(parents=True)
    (root / "a" / "f1.txt").write_text("hello", encoding="utf-8")
    (root / "a" / "f2.pdf").write_text("%PDF", encoding="utf-8")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "x.txt").write_text("secret", encoding="utf-8")
    (root / "b").mkdir()
    (root / "b" / "g.docx").write_text("docx", encoding="utf-8")


def test_bulk_basic(tmp_path: Path):
    from markitdown.bulk_converter import bulk_convert

    src = tmp_path / "src"
    src.mkdir()
    _make_tree(src)

    dest = tmp_path / "out"
    res = bulk_convert(src, dest=dest)

    # Files created with .md extension, hidden skipped
    assert (dest / "a" / "f1.md").exists()
    assert (dest / "a" / "f2.md").exists()
    assert (dest / "b" / "g.md").exists()
    assert not (dest / ".hidden").exists()

    # Report exists
    report = dest / "process_report.md"
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "Bulk Conversion Report" in content
    assert res.converted == 3


def test_conflict_rename(tmp_path: Path):
    from markitdown.bulk_converter import bulk_convert

    src = tmp_path / "src"
    src.mkdir()
    (src / "file.txt").write_text("x", encoding="utf-8")

    dest = tmp_path / "out"
    (dest / "file.md").parent.mkdir(parents=True, exist_ok=True)
    (dest / "file.md").write_text("existing", encoding="utf-8")

    res = bulk_convert(src, dest=dest, on_conflict="rename")
    assert (dest / "file.md").exists()
    assert (dest / "file (1).md").exists()
    assert res.converted == 1


def test_filters_and_skip_policy(tmp_path: Path):
    from markitdown.bulk_converter import bulk_convert

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.pdf").write_text("x", encoding="utf-8")
    (src / "b.docx").write_text("x", encoding="utf-8")

    dest = tmp_path / "out"
    # Using include only pdf
    res = bulk_convert(src, dest=dest, include_ext={"pdf"})
    assert (dest / "a.md").exists()
    assert not (dest / "b.md").exists()
    assert res.converted == 1
    assert res.skipped >= 1


def test_threshold_confirmation(monkeypatch, tmp_path: Path):
    from markitdown.bulk_converter import bulk_convert, BulkConvertThresholds

    src = tmp_path / "src"
    src.mkdir()
    # Create more than threshold files
    for i in range(3):
        (src / f"f{i}.txt").write_text("x", encoding="utf-8")

    dest = tmp_path / "out"

    th = BulkConvertThresholds(max_dirs=1, max_files=2, max_bytes=10)

    # Without confirm -> should raise
    with pytest.raises(Exception):
        bulk_convert(src, dest=dest, thresholds=th, confirm=None)

    # With confirm=False -> raise
    def _deny(stats, th):
        return False

    with pytest.raises(Exception):
        bulk_convert(src, dest=dest, thresholds=th, confirm=_deny)

    # With confirm=True -> proceed
    def _allow(stats, th):
        return True

    res = bulk_convert(src, dest=dest, thresholds=th, confirm=_allow)
    assert res.converted == 3
