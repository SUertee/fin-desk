"""Read-only developer API for runtime capability inspection."""

from functools import lru_cache

from fastapi import APIRouter

from app.agents.specialists import REGISTRY
from app.runtime.capabilities import (
    CapabilityCatalog,
    CapabilityCatalogResponse,
    get_capability_health_service,
)
from app.runtime.orchestration.finance_runtime import FinanceRuntime


router = APIRouter(prefix="/developer/capabilities", tags=["developer"])


@lru_cache(maxsize=1)
def get_capability_runtime() -> FinanceRuntime:
    return FinanceRuntime()


@router.get("", response_model=CapabilityCatalogResponse)
async def list_capabilities() -> CapabilityCatalogResponse:
    runtime = get_capability_runtime()
    status = await get_capability_health_service().vibe_market_data_status()
    catalog = CapabilityCatalog.from_registries(
        runtime.tool_registry,
        REGISTRY,
        optional_tool_statuses={"get_vibe_market_data": status},
    )
    return CapabilityCatalogResponse(
        capabilities=catalog.list(),
    )
