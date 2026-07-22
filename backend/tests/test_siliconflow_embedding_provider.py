import json

import httpx
import pytest

from app.connectors.embeddings import (
    SiliconFlowEmbeddingError,
    SiliconFlowEmbeddingProvider,
)


def _provider(handler, *, api_key="test-secret", dimension=3):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SiliconFlowEmbeddingProvider(
        api_key=api_key,
        model_id="BAAI/bge-m3",
        dimension=dimension,
        base_url="https://siliconflow.test/v1",
        max_batch_size=4,
        client=client,
    )


def test_siliconflow_embeds_batch_and_restores_index_order():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "https://siliconflow.test/v1/embeddings"
        assert request.headers["authorization"] == "Bearer test-secret"
        assert payload == {
            "model": "BAAI/bge-m3",
            "input": ["first", "second"],
            "encoding_format": "float",
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.5]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.5]},
                ],
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )

    vectors = _provider(handler).embed(["first", "second"], purpose="document")

    assert vectors == [[1.0, 0.0, 0.5], [0.0, 1.0, 0.5]]


@pytest.mark.parametrize(
    "data",
    [
        [{"index": 0, "embedding": [1.0, 0.0, 0.5]}],
        [
            {"index": 0, "embedding": [1.0, 0.0, 0.5]},
            {"index": 0, "embedding": [0.0, 1.0, 0.5]},
        ],
        [
            {"index": 0, "embedding": [1.0, 0.0, 0.5]},
            {"index": 1},
        ],
    ],
)
def test_siliconflow_rejects_invalid_indexed_payload(data):
    provider = _provider(lambda _request: httpx.Response(200, json={"data": data}))

    with pytest.raises(SiliconFlowEmbeddingError, match="invalid response"):
        provider.embed(["first", "second"], purpose="query")


def test_siliconflow_maps_http_failure_without_leaking_key_or_body():
    provider = _provider(
        lambda _request: httpx.Response(
            429,
            json={"message": "secret provider response"},
        ),
        api_key="private-key-value",
    )

    with pytest.raises(SiliconFlowEmbeddingError) as captured:
        provider.embed(["query"], purpose="query")

    message = str(captured.value)
    assert "private-key-value" not in message
    assert "secret provider response" not in message
    assert "HTTPStatusError" in message


def test_siliconflow_bounds_configuration_and_input():
    provider = _provider(lambda _request: httpx.Response(500), api_key="")
    with pytest.raises(SiliconFlowEmbeddingError, match="not configured"):
        provider.embed(["query"], purpose="query")

    configured = _provider(lambda _request: httpx.Response(500))
    with pytest.raises(ValueError, match="batch exceeds"):
        configured.embed(["a", "b", "c", "d", "e"], purpose="document")
    assert configured.embed([], purpose="document") == []
