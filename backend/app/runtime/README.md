# runtime/

Runtime owns the agent execution boundary. Routes call runtime, runtime calls
agents/tools/services, and external systems stay behind connectors.

## Structure

```text
runtime/
  orchestration/    # public finance use-case runtime entrypoints
  execution/        # self-hosted multi-agent execution contracts
  llm/              # model provider adapters only
  policy/           # runtime, audit, and cost policies
  observability/    # trace collection and run observations
  contracts/        # output contract validation
  response/         # response composition
```

## Boundaries

- `routes/` must not choose tools or specialists.
- `agents/` must not access connectors directly.
- `tools/` return deterministic evidence and typed observations.
- `connectors/` own external system access and persistence adapters.
- `runtime/orchestration/` coordinates finance request flows and owns use-case wiring.
- `runtime/execution/` defines reusable execution contracts, not finance business logic.
- `runtime/observability/` records what actually happened during a run.
- `runtime/llm/` may call model providers, but must not own orchestration.
