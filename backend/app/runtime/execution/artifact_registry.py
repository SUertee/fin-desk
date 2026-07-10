"""Per-run artifact registry for intermediate evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArtifactRegistry:
    artifacts: dict[str, Any] = field(default_factory=dict)

    def put(self, name: str, value: Any) -> None:
        self.artifacts[name] = value

    def get(self, name: str, default: Any = None) -> Any:
        return self.artifacts.get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.artifacts)
