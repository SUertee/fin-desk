# evals/

Offline harness evaluation assets for the finance agent runtime.

This folder is part of the application harness, not just unit-test scaffolding.
It defines golden scenarios and replay checks that verify agent runs expose the
facts required for debugging, audit, and regression review.

## Files

| Path | Purpose |
|------|---------|
| `fixtures/*.json` | Golden scenarios for CFO chat entrypoints |
| `baselines/offline.json` | Reviewed per-case baseline for the offline gate |
| `samples/ci_traces.jsonl` | Deterministic trace export sample used by harness CI |
| `contracts.py` | Shared task, trial, grader, report, baseline, and gate contracts |
| `suite_adapters.py` | Thin adapters over the existing domain evaluators |
| `harness_runner.py` | Hermetic offline suite runner and regression gate CLI |
| `replay.py` | Loader and matcher for `AgentRunRecord` replay checks |
| `replay_run.py` | CLI/admin helper for replaying persisted run records by request ID |
| `trace_export.py` | Typed JSON/JSONL trace export reader and CI regression report CLI |
| `memory_eval.py` | Deterministic multi-turn memory-window and reference-resolution eval |
| `cfo_runtime_acceptance.py` | Cross-layer response and run-ledger acceptance evaluator |
| `specialist_execution_eval.py` | Offline concurrency, dependency, timeout, and partial-success eval |
| `composed_team_acceptance.py` | End-to-end composed-team acceptance evaluator |

## Run The Unified Offline Gate

Run all deterministic agent eval suites without live LLM, network, PostgreSQL,
Redis, embedding, or MCP dependencies:

```bash
python -m app.evals.harness_runner --output reports/offline-eval-report.json
```

The command evaluates 68 reviewed cases across CFO runtime acceptance,
composed teams, specialist execution, memory, knowledge retrieval, and
investment research. It exits with:

- `0` when the severity-aware regression gate passes.
- `1` when a required case is missing, a blocking regression is found, or a
  current critical or major case fails.
- `2` when the baseline or offline harness configuration is invalid.

The JSON report contains bounded case outcomes, reason codes, the baseline
diff, and the final gate decision. It intentionally excludes response text,
transaction payloads, prompts, and secrets.

Baseline regeneration is a reviewed operation, not a routine way to fix a
failing gate:

```bash
python -m app.evals.harness_runner \
  --write-baseline \
  --output reports/offline-eval-report.json
```

Review every new, removed, or changed case before committing
`baselines/offline.json`.

Run the memory regression set without a model or infrastructure dependency:

```bash
python -m app.evals.memory_eval
```

Run the complete offline CFO runtime acceptance set:

```bash
pytest tests/test_cfo_runtime_acceptance_eval.py -q
```

Run the specialist scheduling regression set:

```bash
python -m app.evals.specialist_execution_eval
```

Run the composed-team acceptance set:

```bash
pytest tests/test_composed_team_acceptance_eval.py -q
```

Its latency and speedup values compare deterministic local fixtures. They detect
accidental serialization but are not production performance claims.

## What The Harness Verifies

- selected agents for the scenario
- expected deterministic tool calls
- response execution facts used by the product UI
- output contract validation facts for `ChatResponse`
- specialist `SpecialistAgentOutput` validation facts from typed handoffs
- usage totals from normalized provider responses
- output contract name
- audit status when required
- entrypoint and user identity consistency
- response and run-ledger execution-fact consistency
- bounded specialist context, evidence join, and partial-team disclosure

The current v1 harness intentionally records input summaries instead of full
financial payloads in logs. Full scenario payloads live in fixtures where they
can be reviewed, versioned, and replayed safely during tests.

Contract validation failures are stored as structured `output_validations`
entries instead of raw exception text. This makes replay useful for debugging
broken agent responses without logging the full financial payload.
Specialist validations are derived from typed `consult_*` tool outputs, so
deterministic evidence tools are not interpreted as agent contracts.

## Replay A Persisted Run

Use the replay CLI when a request already exists in the run ledger:

```bash
python -m app.evals.replay_run req-123 --case-id chat_spending_review
```

The same replay report is exposed through `GET /agent-runs/{request_id}/replay`.
When `case_id` is provided, the report includes the harness evaluation result
for the matching fixture. Without `case_id`, it returns the normalized run
summary for debugging.

## Evaluate Exported Traces In CI

Use the trace export CLI when CI or a local regression job already has one or
more serialized `AgentRunRecord` objects:

```bash
python -m app.evals.trace_export traces.jsonl
```

The export format supports either raw `AgentRunRecord` objects or wrapped
records with an explicit fixture mapping:

```json
{"case_id":"chat_spending_review","record":{"schema_version":"agent-run-record/v2"}}
```

When `case_id` is omitted, the harness attempts to match a fixture by
`entrypoint + user_id`. The CLI exits non-zero for failed evaluations, malformed
records, or unmatched records by default. Use `--allow-skipped` only for broad
debug exports where not every run is expected to have a golden fixture.

To persist the machine-readable CI report:

```bash
python -m app.evals.trace_export traces.jsonl --output reports/trace-report.json
```

The GitHub Actions workflow runs the same command against
`app/evals/samples/ci_traces.jsonl` and uploads `reports/trace-report.json` as a
build artifact.
