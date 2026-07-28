"""Expand declarative teams into atomic executable capabilities."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.runtime.capabilities.catalog import CapabilityCatalog


def expand_team_capabilities(
    capability_ids: Iterable[str],
    catalog: "CapabilityCatalog",
) -> tuple[str, ...]:
    """Return tools and agents in declaration order, rejecting invalid teams."""

    expanded: list[str] = []
    seen: set[str] = set()
    resolving: set[str] = set()

    def visit(capability_id: str) -> None:
        entry = catalog.get(capability_id)
        if entry is None:
            raise ValueError(f"Unknown capability id: {capability_id}")
        if entry.descriptor.kind != "team":
            if capability_id not in seen:
                seen.add(capability_id)
                expanded.append(capability_id)
            return
        if not entry.status.enabled:
            raise ValueError(f"Team capability is disabled: {capability_id}")
        if not entry.status.available:
            raise ValueError(f"Team capability is unavailable: {capability_id}")
        if capability_id in resolving:
            raise ValueError(f"Cyclic team definition: {capability_id}")
        if not entry.descriptor.requires:
            raise ValueError(f"Team capability has no members: {capability_id}")

        resolving.add(capability_id)
        for member_id in entry.descriptor.requires:
            visit(member_id)
        resolving.remove(capability_id)

    for requested_id in dict.fromkeys(capability_ids):
        visit(requested_id)
    return tuple(expanded)
