# Personal Finance Team: OpenAI Agents SDK Architecture Assessment

Date: 2026-06-13

## Direction

The project is now standardized on the OpenAI Agents SDK for agent-backed
finance analysis and chat. The current codebase intentionally avoids a mixed
agent stack: no parallel graph runtime, no deep-agent compatibility layer, and
no direct LLM provider abstraction in the product path.

This keeps the system easier to reason about and stronger for engineering
review: one runtime boundary, one model configuration strategy, and one
testable contract for agent output.

## Current Shape

```text
web/
  React + Vite finance dashboard

backend/
  app/main.py
  app/routes/
    analyze.py        -> OpenAI analysis specialist runtime
    chat.py           -> CFO-first chat runtime
    health.py
    profile.py
    transactions.py
  app/runtime/
    analysis_runtime.py
    cfo_chat_runtime.py
    openai_cfo_runtime.py
    runtime_policy.py
    response_composer.py
    trace_collector.py
  app/agents/
    cfo/
    specialists/
  app/tools/
    deterministic finance evidence tools
  app/repositories/
    PostgreSQL persistence boundary
  app/services/
    deterministic business services
```

## Runtime Boundary

The product API stays stable:

- `POST /analyze` enriches transactions, computes deterministic summaries, and
  asks the Analysis Specialist agent to produce the response JSON contract.
- `POST /chat` builds finance context, evaluates runtime policy, and calls the
  CFO agent through the OpenAI Agents SDK.
- Deterministic tools remain responsible for evidence extraction, anomaly
  summaries, audit payloads, and budget snapshots.

The critical design rule is that agents do not query persistence directly.
Routes, services, repositories, and tools prepare scoped evidence; agents reason
over that evidence and produce user-facing outputs.

## Why This Is Stronger

- The backend has a professional harness boundary under `app/runtime/`.
- Agent output contracts are normalized before reaching the frontend.
- Tests can inject fake runners, so agent behavior is verified without real API
  calls.
- The system avoids fallback behavior that can hide runtime failures.
- Configuration is OpenAI-only: `OPENAI_API_KEY`, model IDs, and max-turns.

## Next Engineering Step

The next high-value milestone is to promote the current controlled specialist
tools into real OpenAI Agents SDK specialists:

- Expense Analyst
- Budget Coach
- Auditor

The CFO agent should remain the orchestrator. Specialist agents should receive
bounded evidence, return typed outputs, and be covered by harness tests that
prove selection, handoff, output validation, and audit behavior.

## Resume Framing

> Engineered an OpenAI Agents SDK-based personal finance multi-agent platform
> with a CFO orchestrator, analysis specialist runtime, deterministic finance
> tools, typed output normalization, trace collection, and regression tests that
> validate agent contracts without live model calls.
