"""Immutable filesystem persistence for offline experiment evidence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from research.quant_lab.contracts import ExperimentArtifact


def write_experiment_artifact(
    artifact: ExperimentArtifact,
    output_root: str | Path,
) -> Path:
    root = Path(output_root)
    target_dir = root / artifact.body.experiment_id
    target = target_dir / "artifact.json"
    payload = artifact.model_dump(mode="json")

    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if existing == payload:
            return target
        raise FileExistsError(
            "experiment id already exists with a different immutable artifact"
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".artifact-",
        suffix=".json",
        dir=target_dir,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
        return target
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def read_experiment_artifact(path: str | Path) -> ExperimentArtifact:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ExperimentArtifact.model_validate(payload)
