"""SiliconFlow vision-language adapter (OpenAI-compatible chat completions).

Images are sent as base64 data URLs because MinIO is local-only: the cloud VL
endpoint cannot resolve a presigned URL pointing at the host network, so the
image bytes are inlined in the request body instead. This keeps the ``vision``
connector independent of the object-storage connector at ingestion time.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.connectors.vision.errors import VisionProviderError
from app.connectors.vision.provider import VLObservation

DEFAULT_CAPTION_PROMPT = (
    "简洁描述这张图片的内容（含图中可见的文字、表格、图表信息），"
    "用于文档语义检索，300字以内，直接给描述不要前缀"
)


class SiliconFlowVisionProvider:
    provider_id = "siliconflow"

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str = "Qwen/Qwen2.5-VL-72B-Instruct",
        base_url: str = "https://api.siliconflow.cn/v1",
        timeout_seconds: int = 60,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model_id = model_id.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.client = client

    def describe_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        *,
        prompt: str = "",
    ) -> VLObservation:
        if not self.api_key:
            raise VisionProviderError("SiliconFlow vision is not configured")
        if not image_bytes:
            raise VisionProviderError("image_bytes must be non-empty")
        effective_prompt = prompt or DEFAULT_CAPTION_PROMPT
        request = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": _build_data_url(image_bytes, mime_type)}},
                        {"type": "text", "text": effective_prompt},
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self.client is not None:
                response = self.client.post(
                    f"{self.base_url}/chat/completions",
                    json=request,
                    headers=headers,
                )
            else:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    json=request,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VisionProviderError(
                f"SiliconFlow vision request failed ({type(exc).__name__})"
            ) from exc
        caption = _extract_content(payload)
        if not caption:
            raise VisionProviderError("SiliconFlow vision returned an empty caption")
        return VLObservation(caption=caption)


def _build_data_url(image_bytes: bytes, mime_type: str) -> str:
    mime = mime_type or "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    # Some providers return content as a list of typed parts.
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return " ".join(str(part).strip() for part in parts if part).strip()
    return ""
