"""Private filesystem storage for statement candidates under review."""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


class StatementFileStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    def save(self, import_id: str, filename: str, content: bytes) -> Path:
        target = self._bucket("processing") / f"{import_id}-{_safe_name(filename)}"
        target.write_bytes(content)
        return target

    def move(self, source: str | Path, bucket: str) -> Path:
        source_path = self._resolve(source)
        if bucket == "archive":
            now = datetime.now(timezone.utc)
            target_dir = self._bucket(f"archive/{now:%Y/%m}")
        else:
            target_dir = self._bucket(bucket)
        target = target_dir / source_path.name
        if source_path != target:
            shutil.move(str(source_path), target)
        return target

    def read(self, stored_path: str) -> bytes:
        return self._resolve(stored_path).read_bytes()

    def reference(self, path: str | Path) -> str:
        return str(self._resolve(path).relative_to(self.root))

    def _bucket(self, name: str) -> Path:
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("invalid statement storage bucket")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.root / candidate).resolve()
        )
        if not resolved.is_relative_to(self.root):
            raise ValueError("statement path is outside private storage")
        return resolved


def _safe_name(filename: str) -> str:
    basename = Path(filename or "statement").name
    clean = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", basename)
    return clean[:180] or "statement"
