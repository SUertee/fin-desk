"""Create an immutable Qlib workflow configuration from a typed spec."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.quant_lab.contracts import QuantExperimentSpec
from research.quant_lab.qlib_workflow import (
    build_qlib_workflow_config,
    write_workflow_config,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--provider-uri", required=True)
    parser.add_argument("--market-name", default="all")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    spec = QuantExperimentSpec.model_validate_json(
        args.spec.read_text(encoding="utf-8")
    )
    config = build_qlib_workflow_config(
        spec,
        provider_uri=args.provider_uri,
        market_name=args.market_name,
    )
    target = write_workflow_config(config, args.output)
    print(json.dumps({"workflow": str(target), "experiment": spec.experiment_name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
