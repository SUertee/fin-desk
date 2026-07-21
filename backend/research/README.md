# FinDesk Quant Research Lab

This package is an offline research boundary. It consumes FinDesk
`MarketPriceHistory` contracts, builds content-addressed dataset snapshots, and
prepares Qlib workflows. It is not imported by FastAPI and cannot execute trades.

## Environment

```bash
cd backend
python -m venv .venv-research
source .venv-research/bin/activate
pip install -r requirements.txt
pip install -r research/requirements-research.txt
```

The main backend environment deliberately does not include Qlib or LightGBM.

## Dataset Boundary

Export a JSON array of FinDesk `MarketPriceHistory` objects, then build an
immutable raw snapshot:

```bash
cd backend
python -m research.cli.build_dataset \
  --input /path/to/histories.json \
  --output reports/quant_research/datasets
```

The output contains per-symbol CSV files, an instrument list, and a manifest
with provenance and a SHA-256 content hash. Convert the raw CSVs into a Qlib
provider directory with Qlib's data-dump tooling before running a workflow.

To retrieve the initial ETF research universe through FinDesk's governed
`MarketDataService` boundary, run:

```bash
python -m research.cli.export_etf_dataset \
  --symbols SPY,QQQ,TLT,GLD,VNQ \
  --date-from 2020-01-01 \
  --date-to 2025-12-31 \
  --output reports/quant_research/datasets
```

The MVP command is strict: failed chunks, inconsistent currencies, duplicate
dates, or invalid provider ranges prevent snapshot creation and return a
non-zero exit. Trading-calendar validation and partial recovery are deliberately
deferred until the first experiment demonstrates a concrete need.

## Workflow

Prepare a workflow from a strict experiment spec:

```bash
python -m research.cli.prepare_workflow \
  --spec /path/to/experiment.json \
  --provider-uri /path/to/qlib/provider \
  --output reports/quant_research/workflows/etf-lightgbm.yaml

python -m research.cli.run_workflow \
  --config reports/quant_research/workflows/etf-lightgbm.yaml
```

The Qlib invocation uses `shell=false`, a timeout, and bounded output capture.
Its output must still be normalized into an immutable `ExperimentArtifact`
before FinDesk may display it as research evidence.
