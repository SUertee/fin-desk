import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/analyze"),
        ("get", "/schema"),
    ],
)
async def test_removed_analysis_routes_return_not_found(method, path):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        response = await getattr(client, method)(path)

    assert response.status_code == 404
