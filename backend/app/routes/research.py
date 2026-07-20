"""Internal governed web-research API."""

from fastapi import APIRouter, HTTPException

from app.connectors.web_search.errors import WebSearchBudgetExceeded
from app.models.web_research import (
    WebResearchRequest,
    WebResearchResult,
    WebSearchProviderStatus,
)
from app.services.web_research import build_web_research_service


router = APIRouter(prefix="/research", tags=["research"])
_service = build_web_research_service()


@router.get("/providers/status", response_model=WebSearchProviderStatus)
def provider_status() -> WebSearchProviderStatus:
    return _service.get_provider_status()


@router.post("/search", response_model=WebResearchResult)
def search_research(request: WebResearchRequest) -> WebResearchResult:
    try:
        return _service.search(request, budget=_service.new_budget())
    except WebSearchBudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
