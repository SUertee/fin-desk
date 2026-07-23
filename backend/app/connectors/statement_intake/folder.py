"""Low-cost top-level scanner for a user-configured statement inbox."""

from __future__ import annotations

import os
import time
from pathlib import Path

_SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".pdf"}


class StatementFolderScanner:
    def __init__(self, root: Path, *, stable_seconds: int, max_file_bytes: int):
        self.root = root.expanduser().resolve()
        self.stable_seconds = stable_seconds
        self.max_file_bytes = max_file_bytes

    def scan(self, subdirectory: str = "") -> list[Path]:
        target = (self.root / subdirectory).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("statement inbox subdirectory escapes configured root")
        target.mkdir(parents=True, exist_ok=True)
        now = time.time()
        ready: list[Path] = []
        with os.scandir(target) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False):
                    continue
                path = Path(entry.path)
                if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                    continue
                stat = entry.stat(follow_symlinks=False)
                if stat.st_size > self.max_file_bytes:
                    continue
                if now - stat.st_mtime < self.stable_seconds:
                    continue
                ready.append(path)
        return sorted(ready)
