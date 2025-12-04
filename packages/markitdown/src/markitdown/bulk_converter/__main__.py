from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from ._bulk import (
    bulk_convert,
    BulkConvertThresholds,
    PreflightExceeded,
)


def _prompt_confirm(stats_text: str) -> bool:
    try:
        answer = input(stats_text + " Proceed? [y/N]: ").strip().lower()
        return answer in ("y", "yes")
    except EOFError:
        return False


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Bulk convert a directory tree to Markdown")
    p.add_argument("root", help="Root directory to scan for input files")
    p.add_argument("--dest", default=None, help="Destination root (default: create md-sibling)")
    p.add_argument("--include", nargs="*", default=None, help="Only convert these extensions (e.g., pdf docx)")
    p.add_argument("--exclude", nargs="*", default=None, help="Skip these extensions")
    p.add_argument(
        "--on-conflict",
        choices=["rename", "skip"],
        default="rename",
        help="When output exists, either rename with numeric suffix or skip",
    )
    p.add_argument("--enable-plugins", action="store_true", help="Enable markitdown plugins")
    p.add_argument("--no-continue-on-error", action="store_true", help="Stop on first error")
    p.add_argument("--no-skip-hidden", action="store_true", help="Include hidden files and directories")
    p.add_argument("--threshold-dirs", type=int, default=16, help="Max directories before confirmation is required")
    p.add_argument("--threshold-files", type=int, default=128, help="Max files before confirmation is required")
    p.add_argument("--threshold-mb", type=int, default=300, help="Max total size (MiB) before confirmation is required")
    p.add_argument("--yes", "-y", action="store_true", help="Auto-confirm running above thresholds")

    args = p.parse_args(argv)

    thresholds = BulkConvertThresholds(
        max_dirs=args.threshold_dirs,
        max_files=args.threshold_files,
        max_bytes=args.threshold_mb * 1024 * 1024,
    )

    def confirm(stats, thres) -> bool:  # type: ignore[no-redef]
        if args.yes:
            return True
        stats_text = (
            f"Preflight limits exceeded. Dirs: {stats.dirs}/{thres.max_dirs}, "
            f"Files: {stats.files}/{thres.max_files}, Size: {stats.bytes}/{thres.max_bytes} bytes."
        )
        return _prompt_confirm(stats_text)

    try:
        result = bulk_convert(
            root=args.root,
            dest=args.dest,
            include_ext=set(args.include) if args.include else None,
            exclude_ext=set(args.exclude) if args.exclude else None,
            on_conflict=args.on_conflict,  # type: ignore[arg-type]
            workers=None,
            continue_on_error=not args.no_continue_on_error,
            enable_plugins=True if args.enable_plugins else None,
            thresholds=thresholds,
            confirm=confirm,
            skip_hidden=not args.no_skip_hidden,
        )
        print(result.to_summary())
        print(f"Report written to: {Path(result.dest) / 'process_report.md'}")
        return 0 if result.failed == 0 or not args.no_continue_on_error else 1
    except PreflightExceeded as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:  # pragma: no cover - general safeguard
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
