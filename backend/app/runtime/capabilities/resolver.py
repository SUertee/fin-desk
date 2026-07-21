"""Deterministic capability binding with explicit policy rejection."""

from __future__ import annotations

from collections.abc import Set

from app.runtime.capabilities.catalog import CapabilityCatalog
from app.runtime.capabilities.contracts import (
    CapabilityKind,
    CapabilityResolution,
    CapabilityResolutionStatus,
)


class CapabilityResolver:
    def __init__(self, catalog: CapabilityCatalog):
        self.catalog = catalog

    def resolve(
        self,
        capability_id: str,
        *,
        granted_capabilities: Set[str],
        expected_kind: CapabilityKind | None = None,
    ) -> CapabilityResolution:
        entry = self.catalog.get(capability_id)
        if entry is None:
            return _rejected(capability_id, "unknown", "Capability is not registered")
        if not entry.status.enabled:
            return _rejected(
                capability_id,
                "disabled",
                entry.status.reason or "Capability is disabled",
            )
        if not entry.status.available:
            return _rejected(
                capability_id,
                "unavailable",
                entry.status.reason or "Capability is unavailable",
            )
        if capability_id not in granted_capabilities:
            return _rejected(
                capability_id,
                "disallowed",
                "Capability is not granted by current policy",
            )
        if entry.implementation is None:
            return _rejected(
                capability_id,
                "unavailable",
                "Capability implementation is unavailable",
            )
        if expected_kind is not None and (
            entry.descriptor.kind != expected_kind
            or entry.implementation.kind != expected_kind
        ):
            return _rejected(
                capability_id,
                "disallowed",
                f"Capability kind must be {expected_kind}",
            )
        return CapabilityResolution(
            capability_id=capability_id,
            status="resolved",
            reference=entry.implementation,
        )


def _rejected(
    capability_id: str,
    status: CapabilityResolutionStatus,
    reason: str,
) -> CapabilityResolution:
    return CapabilityResolution(
        capability_id=capability_id,
        status=status,
        reason=reason,
    )
