# Agent Gateway

This package is the external agent interoperability boundary for the Finance
Workspace. It is intentionally protocol-neutral.

- `agent_profile.py` declares the public Finance CFO agent identity and
  capabilities.
- `task_contracts.py` defines stable request/response models used by routes,
  protocol adapters, and future task ledgers.
- `inbound_gateway.py` accepts external agent tasks and translates them into the
  internal `FinanceRuntime`.
- `outbound_gateway.py` is the future boundary for Finance calling other
  personal agents.
- `adapters/` owns protocol-specific mappings such as A2A. Protocol names should
  stay here instead of becoming top-level application folders.

The Finance runtime remains responsible for internal multi-agent orchestration.
The gateway only owns cross-agent interoperability.
