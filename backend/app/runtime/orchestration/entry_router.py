"""Compatibility shim — the entry router now lives in the `router` package.

See `app/runtime/orchestration/router/` for the two-layer architecture:
semantic intent recognition (rules + model) and deterministic route
resolution. This module only re-exports the public facade.
"""

from app.runtime.orchestration.router import EntryRouter

__all__ = ["EntryRouter"]
