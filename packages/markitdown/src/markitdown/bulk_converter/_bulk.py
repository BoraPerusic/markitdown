from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Literal, Optional, Tuple

from .._base_converter import DocumentConverterResult
from .._markitdown import MarkItDown
from .types import BulkFileResult, BulkResult


ConflictPolicy = Literal["rename", "skip"]


@dataclass(frozen=True)
class BulkConvertThresholds:
    max_dirs: int = 16
    max_files: int = 128
    max_bytes: int = 300 * 1024 * 1024  # 300 MB


@dataclass(frozen=True)
class PreflightStats:
    root: Path
    dirs: int
    files: int
    bytes: int


class PreflightExceeded(Exception):
    def __init__(self, stats: PreflightStats, thresholds: BulkConvertThresholds):
        super().__init__(
            f"Preflight limits exceeded: dirs={stats.dirs}/{thresholds.max_dirs}, "
            f"files={stats.files}/{thresholds.max_files}, bytes={stats.bytes}/{thresholds.max_bytes}"
        )
        self.stats = stats
        self.thresholds = thresholds


def _is_hidden(path: Path) -> bool:
    name = path.name
    return name.startswith(".") and name not in (".", "..")


def _md_sibling_dest(root: Path) -> Path:
    parent = root.parent
    name = root.name + "-md"
    return parent / name


def _iter_files(root: Path, skip_hidden: bool) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        if skip_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if skip_hidden and fn.startswith("."):
                continue
            yield dp / fn


def _preflight(root: Path, skip_hidden: bool) -> PreflightStats:
    dirs = 0
    files = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root):
        if skip_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        dirs += 1
        files += len([f for f in filenames if not (skip_hidden and f.startswith("."))])
        for f in filenames:
            if skip_hidden and f.startswith("."):
                continue
            try:
                st = os.stat(os.path.join(dirpath, f))
                total_bytes += int(st.st_size)
            except OSError:
                # If file disappears or is unreadable, ignore for size tally
                pass
    return PreflightStats(root=root, dirs=dirs, files=files, bytes=total_bytes)


def _ext_of(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _derive_output_path(src: Path, root: Path, dest_root: Path) -> Path:
    rel = src.relative_to(root)
    target = dest_root / rel
    return target.with_suffix(".md")


def _unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    parent = p.parent
    i = 1
    pattern = re.compile(r" \((\d+)\)$")
    base_stem = stem
    m = pattern.search(stem)
    if m:
        base_stem = stem[: m.start()]
    while True:
        cand = parent / f"{base_stem} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


def _count_words_and_headings(markdown: str) -> Tuple[int, int]:
    words = len(markdown.split())
    headings = sum(1 for line in markdown.splitlines() if line.lstrip().startswith("#"))
    return words, headings


def _write_atomic(dest_path: Path, data: str) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_path.with_suffix(dest_path.suffix + ".tmp")
    with io.open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    os.replace(tmp, dest_path)


def _make_report(result: BulkResult) -> str:
    # Build per-directory statistics
    from collections import defaultdict

    per_dir_counts: dict[Path, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_dir_docs: dict[Path, int] = defaultdict(int)
    per_dir_words: dict[Path, int] = defaultdict(int)
    per_dir_headings: dict[Path, int] = defaultdict(int)
    errors: list[Tuple[Path, str]] = []

    for fr in result.files:
        d = (fr.dest or result.dest).parent if fr.dest else (result.dest)
        src_dir = fr.src.parent
        if fr.status == "converted" and fr.dest:
            per_dir_counts[src_dir][_ext_of(fr.src)] += 1
            per_dir_docs[src_dir] += 1
            if fr.words:
                per_dir_words[src_dir] += fr.words
            if fr.headings:
                per_dir_headings[src_dir] += fr.headings
        elif fr.status == "failed":
            errors.append((fr.src, fr.reason or "unknown error"))

    lines: list[str] = []
    lines.append(f"# Bulk Conversion Report\n")
    lines.append(f"Root: {result.root}\n")
    lines.append(f"Destination: {result.dest}\n")
    lines.append("")
    lines.append(f"## Summary\n")
    lines.append(f"- Converted: {result.converted}")
    lines.append(f"- Skipped: {result.skipped}")
    lines.append(f"- Failed: {result.failed}")
    lines.append(f"- Total words: {result.total_words}")
    lines.append(f"- Total headings: {result.total_headings}\n")
    lines.append("")
    lines.append("## By Directory\n")
    for d in sorted(per_dir_docs.keys(), key=lambda p: str(p)):
        lines.append(f"### {d}")
        counts = per_dir_counts[d]
        if counts:
            lines.append("- Files converted by type:")
            for ext, cnt in sorted(counts.items()):
                lines.append(f"  - .{ext}: {cnt}")
        lines.append(f"- Documents: {per_dir_docs[d]}")
        lines.append(f"- Words: {per_dir_words[d]}")
        lines.append(f"- Headings: {per_dir_headings[d]}\n")

    if errors:
        lines.append("## Errors\n")
        for src, reason in errors:
            lines.append(f"- {src}: {reason}")

    return "\n".join(lines) + "\n"


def bulk_convert(
    root: str | Path,
    dest: str | Path | None = None,
    *,
    include_ext: Optional[set[str]] = None,
    exclude_ext: Optional[set[str]] = None,
    on_conflict: ConflictPolicy = "rename",
    workers: Optional[int] = None,  # kept for future use; current impl is serial
    continue_on_error: bool = True,
    enable_plugins: Optional[bool] = None,
    thresholds: Optional[BulkConvertThresholds] = None,
    confirm: Optional[Callable[[PreflightStats, BulkConvertThresholds], bool]] = None,
    skip_hidden: bool = True,
) -> BulkResult:
    src_root = Path(root).resolve()
    if not src_root.exists() or not src_root.is_dir():
        raise NotADirectoryError(f"Root path does not exist or is not a directory: {src_root}")

    dest_root = Path(dest).resolve() if dest else _md_sibling_dest(src_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    thresholds = thresholds or BulkConvertThresholds()

    # Preflight
    stats = _preflight(src_root, skip_hidden=skip_hidden)
    exceeded = (
        stats.dirs > thresholds.max_dirs
        or stats.files > thresholds.max_files
        or stats.bytes > thresholds.max_bytes
    )
    if exceeded:
        if confirm is not None:
            if not confirm(stats, thresholds):
                raise PreflightExceeded(stats, thresholds)
        else:
            # No way to confirm -> raise informative exception
            raise PreflightExceeded(stats, thresholds)

    if include_ext:
        include_ext = {e.lower().lstrip('.') for e in include_ext}
    if exclude_ext:
        exclude_ext = {e.lower().lstrip('.') for e in exclude_ext}

    converter = MarkItDown(enable_plugins=enable_plugins) if enable_plugins is not None else MarkItDown()

    results: list[BulkFileResult] = []
    converted = skipped = failed = 0
    total_words = total_headings = 0

    for file_path in _iter_files(src_root, skip_hidden=skip_hidden):
        if include_ext and _ext_of(file_path) not in include_ext:
            results.append(BulkFileResult(src=file_path, dest=None, status="skipped", reason="filtered"))
            skipped += 1
            continue
        if exclude_ext and _ext_of(file_path) in exclude_ext:
            results.append(BulkFileResult(src=file_path, dest=None, status="skipped", reason="filtered"))
            skipped += 1
            continue

        out_path = _derive_output_path(file_path, src_root, dest_root)
        try:
            doc: DocumentConverterResult = converter.convert_local(str(file_path))
            md_text = doc.markdown if hasattr(doc, "markdown") else str(doc)
            words, headings = _count_words_and_headings(md_text)

            final_out = out_path
            if on_conflict == "rename":
                final_out = _unique_path(final_out)
            elif on_conflict == "skip" and final_out.exists():
                results.append(BulkFileResult(src=file_path, dest=None, status="skipped", reason="exists"))
                skipped += 1
                continue

            _write_atomic(final_out, md_text)
            results.append(BulkFileResult(src=file_path, dest=final_out, status="converted", words=words, headings=headings))
            converted += 1
            total_words += words
            total_headings += headings
        except Exception as e:
            failed += 1
            results.append(BulkFileResult(src=file_path, dest=None, status="failed", reason=str(e)))
            if not continue_on_error:
                break

    bulk = BulkResult(
        root=src_root,
        dest=dest_root,
        files=results,
        converted=converted,
        skipped=skipped,
        failed=failed,
        total_words=total_words,
        total_headings=total_headings,
    )

    # Write process_report.md into dest root
    report_text = _make_report(bulk)
    _write_atomic(dest_root / "process_report.md", report_text)

    return bulk
