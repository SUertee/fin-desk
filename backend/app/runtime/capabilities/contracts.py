"""Public contracts for capability discovery and resolution."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CapabilityKind = Literal["tool", "agent", "skill"]
CapabilitySource = Literal["internal", "mcp"]
CapabilityRiskLevel = Literal["low", "medium", "high"]
CapabilityExecutionMode = Literal["read_only", "analysis"]
CapabilityResolutionStatus = Literal[
    "resolved",
    "unknown",
    "disabled",
    "unavailable",
    "disallowed",
]


class CapabilityDescriptor(BaseModel):
    """Stable semantic metadata with no executable or connection details."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    capability_id: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    )
    kind: CapabilityKind
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    source: CapabilitySource = "internal"
    owner: str = Field(min_length=1, max_length=80)
    risk_level: CapabilityRiskLevel
    execution_mode: CapabilityExecutionMode
    input_contract: str = Field(min_length=1, max_length=100)
    output_contract: str = Field(min_length=1, max_length=100)


class CapabilityRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    enabled: bool = True
    available: bool = True
    reason: str = Field(default="", max_length=160)


class CapabilityCatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    descriptor: CapabilityDescriptor
    status: CapabilityRuntimeStatus


class CapabilityCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    capabilities: tuple[CapabilityCatalogItem, ...]


class CapabilityImplementationReference(BaseModel):
    """Opaque registry lookup key; it cannot invoke the implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    capability_id: str
    kind: CapabilityKind
    registry_name: str = Field(min_length=1, max_length=100)


class CapabilityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    capability_id: str
    status: CapabilityResolutionStatus
    reference: CapabilityImplementationReference | None = None
    reason: str = Field(default="", max_length=160)
