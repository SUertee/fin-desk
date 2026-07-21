"""Capability discovery contracts; execution remains in existing registries."""

from app.runtime.capabilities.binding import (
    BoundCapabilityStep,
    BoundExecutionPlan,
    CapabilityBindingError,
    bind_execution_plan,
)
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
from app.runtime.capabilities.health import (
    CapabilityHealthService,
    get_capability_health_service,
)

__all__ = [
    "BoundCapabilityStep",
    "BoundExecutionPlan",
    "CapabilityBindingError",
    "CapabilityCatalog",
    "CapabilityCatalogItem",
    "CapabilityCatalogResponse",
    "CapabilityDescriptor",
    "CapabilityEntry",
    "CapabilityImplementationReference",
    "CapabilityResolution",
    "CapabilityResolver",
    "CapabilityRuntimeStatus",
    "CapabilityHealthService",
    "get_capability_health_service",
    "bind_execution_plan",
]
