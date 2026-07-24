# agents/

CFO-first agent definitions for the FinDesk server.

## Current Shape

The default `/chat` path runs the self-hosted CFO agent loop. The CFO chooses
conversation, clarification, or registered capabilities through a strict
decision contract. The runtime owns policy, binding, and execution;
specialists execute as
`run(SpecialistInput) -> SpecialistAgentOutput` modules resolved from
`specialists.REGISTRY` by the runtime's `SpecialistRunner`.

## Files

| Path | Description |
|------|-------------|
| `specialists/expense_analyst.py` | Spending review run-module (registry) |
| `specialists/budget_coach.py` | Budget guidance run-module (registry) |
| `specialists/auditor.py` | Evidence/risk review over peer outputs (registry) |
| `specialists/market_context.py` | Policy-gated market/news facts with mandatory sources (registry) |
| `specialists/contracts.py` | `SpecialistInput` / `SpecialistAgentOutput` typed contracts |
| `specialists/__init__.py` | `REGISTRY` mapping specialist names to run-modules |
| `cfo/decision.py` | Strict CFO turn-decision contract and model boundary |

## Runtime Boundary

Runtime execution lives in `app/runtime/`. Agent modules should not directly
query connectors or database sessions; data access flows through bounded
tools, services, and connectors. The registry is the seam where an LLM-backed
specialist can replace a deterministic one without touching the orchestrator,
contracts, traces, or evals.
