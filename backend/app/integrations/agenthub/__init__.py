"""Agent Hub integration (serve mode, protocol 0.1).

Read-only projection of existing FinDesk data onto the Agent Hub protocol:
manifest / state / runs / roster plus an A2A-style agent card. No business
logic is duplicated here and nothing outside this package is modified.
"""

from app.integrations.agenthub.router import router

__all__ = ["router"]
