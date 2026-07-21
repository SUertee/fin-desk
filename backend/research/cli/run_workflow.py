"""Run a Qlib workflow in the dedicated research environment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.quant_lab.qlib_workflow import SubprocessQlibRunner


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--qrun", default="qrun")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    result = SubprocessQlibRunner(
        executable=args.qrun,
        timeout_seconds=args.timeout,
    ).run(args.config)
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
