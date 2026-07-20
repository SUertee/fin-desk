import pytest
from fastapi import HTTPException

from app.connectors.web_search.errors import WebSearchBudgetExceeded
from app.models.web_research import WebSearchProviderStatus
from app.routes import research as route


class FailingService:
    def __init__(self, error):
        self.error = error

    def new_budget(self):
        return object()

    def search(self, *_args, **_kwargs):
        raise self.error


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (ValueError("domain not allowlisted"), 400),
        (WebSearchBudgetExceeded("budget exhausted"), 429),
    ],
)
def test_search_route_maps_bounded_request_errors(monkeypatch, error, status_code):
    monkeypatch.setattr(route, "_service", FailingService(error))

    with pytest.raises(HTTPException) as raised:
        route.search_research({"query": "latest market news"})

    assert raised.value.status_code == status_code


def test_provider_status_does_not_make_search_request(monkeypatch):
    expected = WebSearchProviderStatus(
        availability="available",
        configured_provider="tavily",
        allowed=True,
    )

    class StatusService:
        def get_provider_status(self):
            return expected

    monkeypatch.setattr(route, "_service", StatusService())

    assert route.provider_status() == expected
