"""SiliconFlow adapter for FinDesk's provider-neutral embedding contract."""

from __future__ import annotations

from typing import Any

import httpx

from app.knowledge.embeddings import EmbeddingPurpose, validate_embedding_batch


class SiliconFlowEmbeddingError(RuntimeError):
    """Stable error boundary that never includes credentials or response bodies."""


class SiliconFlowEmbeddingProvider:
    provider_id = "siliconflow"

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str = "BAAI/bge-m3",
        dimension: int = 1024,
        base_url: str = "https://api.siliconflow.cn/v1",
        timeout_seconds: int = 20,
        max_batch_size: int = 32,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model_id = model_id.strip()
        self.dimension = int(dimension)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_batch_size = max_batch_size
        self.client = client

    def embed(
        self,
        texts: list[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> list[list[float]]:
        del purpose  # SiliconFlow uses the same endpoint for documents and queries.
        if not self.api_key:
            raise SiliconFlowEmbeddingError("SiliconFlow embeddings are not configured")
        if not texts:
            return []
        if len(texts) > self.max_batch_size:
            raise ValueError("embedding batch exceeds the configured limit")
        normalized = [text.strip() for text in texts]
        if any(not text or len(text) > 20_000 for text in normalized):
            raise ValueError("embedding input must contain 1 to 20000 characters")

        request = {
            "model": self.model_id,
            "input": normalized,
            "encoding_format": "float",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self.client is not None:
                response = self.client.post(
                    f"{self.base_url}/embeddings",
                    json=request,
                    headers=headers,
                )
            else:
                response = httpx.post(
                    f"{self.base_url}/embeddings",
                    json=request,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
            vectors = self._ordered_vectors(payload, expected_count=len(normalized))
            return validate_embedding_batch(self, normalized, vectors)
        except SiliconFlowEmbeddingError:
            raise
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise SiliconFlowEmbeddingError(
                f"SiliconFlow embedding request failed ({type(exc).__name__})"
            ) from exc

    @staticmethod
    def _ordered_vectors(
        payload: Any,
        *,
        expected_count: int,
    ) -> list[list[float]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SiliconFlowEmbeddingError("SiliconFlow returned an invalid response")
        indexed: dict[int, list[float]] = {}
        for item in payload["data"]:
            if not isinstance(item, dict):
                raise SiliconFlowEmbeddingError("SiliconFlow returned an invalid response")
            index = item.get("index")
            vector = item.get("embedding")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or not isinstance(vector, list)
                or index in indexed
            ):
                raise SiliconFlowEmbeddingError("SiliconFlow returned an invalid response")
            indexed[index] = vector
        if set(indexed) != set(range(expected_count)):
            raise SiliconFlowEmbeddingError("SiliconFlow returned an invalid response")
        return [indexed[index] for index in range(expected_count)]
