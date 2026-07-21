"""Read-only capability projection over existing execution registries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.agents.specialists import SpecialistRun
from app.runtime.capabilities.contracts import (
    CapabilityCatalogItem,
    CapabilityDescriptor,
    CapabilityImplementationReference,
    CapabilityRuntimeStatus,
)
from app.runtime.capabilities.definitions import (
    SPECIALIST_CAPABILITY_DEFINITIONS,
    TOOL_CAPABILITY_DEFINITIONS,
    CapabilityDefinition,
)
from app.runtime.execution import ToolRegistry


@dataclass(frozen=True)
class CapabilityEntry:
    descriptor: CapabilityDescriptor
    status: CapabilityRuntimeStatus
    implementation: CapabilityImplementationReference


class CapabilityCatalog:
    """Sorted metadata catalog that deliberately stores no executors."""

    def __init__(self, entries: Iterable[CapabilityEntry]):
        by_id: dict[str, CapabilityEntry] = {}
        for entry in entries:
            capability_id = entry.descriptor.capability_id
            if capability_id in by_id:
                raise ValueError(f"Duplicate capability id: {capability_id}")
            by_id[capability_id] = entry
        self._entries = dict(sorted(by_id.items()))

    @classmethod
    def from_registries(
        cls,
        tool_registry: ToolRegistry,
        specialist_registry: Mapping[str, SpecialistRun],
        *,
        tool_definitions: Mapping[str, CapabilityDefinition] | None = None,
        specialist_definitions: Mapping[str, CapabilityDefinition] | None = None,
    ) -> "CapabilityCatalog":
        tools = (
            tool_definitions
            if tool_definitions is not None
            else TOOL_CAPABILITY_DEFINITIONS
        )
        specialists = (
            specialist_definitions
            if specialist_definitions is not None
            else SPECIALIST_CAPABILITY_DEFINITIONS
        )
        entries: list[CapabilityEntry] = []

        for spec in tool_registry.available():
            definition = _required_definition(spec.name, tools, "tool")
            entries.append(
                CapabilityEntry(
                    descriptor=definition.descriptor(
                        fallback_description=spec.description
                    ),
                    status=CapabilityRuntimeStatus(),
                    implementation=CapabilityImplementationReference(
                        capability_id=definition.capability_id,
                        kind="tool",
                        registry_name=spec.name,
                    ),
                )
            )

        for name in specialist_registry:
            definition = _required_definition(name, specialists, "specialist")
            entries.append(
                CapabilityEntry(
                    descriptor=definition.descriptor(),
                    status=CapabilityRuntimeStatus(),
                    implementation=CapabilityImplementationReference(
                        capability_id=definition.capability_id,
                        kind="agent",
                        registry_name=name,
                    ),
                )
            )
        return cls(entries)

    def list(self) -> tuple[CapabilityCatalogItem, ...]:
        return tuple(
            CapabilityCatalogItem(descriptor=entry.descriptor, status=entry.status)
            for entry in self._entries.values()
        )

    def get(self, capability_id: str) -> CapabilityEntry | None:
        return self._entries.get(capability_id)


def _required_definition(
    name: str,
    definitions: Mapping[str, CapabilityDefinition],
    registry_kind: str,
) -> CapabilityDefinition:
    definition = definitions.get(name)
    if definition is None:
        raise ValueError(f"Missing capability definition for {registry_kind}: {name}")
    return definition
