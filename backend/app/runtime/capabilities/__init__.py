"""Capability discovery contracts; execution remains in existing registries."""

from app.runtime.capabilities.catalog import CapabilityCatalog, CapabilityEntry
from app.runtime.capabilities.contracts import (
    CapabilityCatalogItem,
    CapabilityCatalogResponse,
    CapabilityDescriptor,
    CapabilityImplementationReference,
    CapabilityResolution,
    CapabilityRuntimeStatus,
)
from app.runtime.capabilities.resolver import CapabilityResolver

__all__ = [
    "CapabilityCatalog",
    "CapabilityCatalogItem",
    "CapabilityCatalogResponse",
    "CapabilityDescriptor",
    "CapabilityEntry",
    "CapabilityImplementationReference",
    "CapabilityResolution",
    "CapabilityResolver",
    "CapabilityRuntimeStatus",
]
