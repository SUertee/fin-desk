"""Read-only developer API for runtime capability inspection."""

from functools import lru_cache

from fastapi import APIRouter

from app.agents.specialists import REGISTRY
from app.runtime.capabilities import CapabilityCatalog, CapabilityCatalogResponse
from app.runtime.orchestration.finance_runtime import FinanceRuntime


router = APIRouter(prefix="/developer/capabilities", tags=["developer"])


@lru_cache(maxsize=1)
def get_capability_catalog() -> CapabilityCatalog:
    runtime = FinanceRuntime()
    return CapabilityCatalog.from_registries(runtime.tool_registry, REGISTRY)


@router.get("", response_model=CapabilityCatalogResponse)
def list_capabilities() -> CapabilityCatalogResponse:
    return CapabilityCatalogResponse(
        capabilities=get_capability_catalog().list(),
    )
