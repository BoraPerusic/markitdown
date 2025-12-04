from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional


Status = Literal["converted", "skipped", "failed"]


@dataclass(frozen=True)
class BulkFileResult:
    src: Path
    dest: Optional[Path]
    status: Status
    reason: Optional[str] = None
    words: Optional[int] = None
    headings: Optional[int] = None


@dataclass(frozen=True)
class BulkResult:
    root: Path
    dest: Path
    files: list[BulkFileResult]
    converted: int
    skipped: int
    failed: int
    total_words: int
    total_headings: int

    def to_summary(self) -> str:
        return (
            f"Converted: {self.converted}, Skipped: {self.skipped}, Failed: {self.failed}, "
            f"Words: {self.total_words}, Headings: {self.total_headings}"
        )
