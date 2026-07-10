"""DeepSeek provider adapter (OpenAI-compatible chat completions).

Implements the `LLMClient` protocol against DeepSeek's official API
(platform.deepseek.com). Model, base URL, and key env come from model
profiles — nothing outside runtime/llm imports the provider SDK.
"""

from __future__ import annotations

import os
from typing import Any

from app.config.settings import ModelProfile, load_model_profiles
from app.models.runtime import AgentRunUsage
from app.runtime.llm.client import LLMResponse

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekTextClient:
    """Thin chat-completions client; one call per generate, usage reported."""

    def __init__(self, profiles: dict[str, ModelProfile] | None = None):
        self._profiles = profiles or load_model_profiles()
        self._client = None

    def _profile(self, name: str) -> ModelProfile:
        profile = self._profiles.get(name)
        if profile is None:
            profile = ModelProfile(name=name, provider="deepseek", model=DEFAULT_MODEL)
        return profile

    @staticmethod
    def api_key(profile: ModelProfile | None = None) -> str:
        key_env = getattr(profile, "api_key_env", "") or "DEEPSEEK_API_KEY"
        return os.getenv(key_env, "")

    def available(self, profile_name: str = "chat") -> bool:
        return bool(self.api_key(self._profile(profile_name)))

    def _ensure_client(self, profile: ModelProfile):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self.api_key(profile),
                base_url=getattr(profile, "api_base_url", "") or DEFAULT_BASE_URL,
                timeout=profile.timeout_seconds,
            )
        return self._client

    async def generate_text(
        self,
        prompt: str,
        *,
        profile: str = "chat",
        system: str = "",
    ) -> LLMResponse:
        model_profile = self._profile(profile)
        client = self._ensure_client(model_profile)
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=model_profile.model or DEFAULT_MODEL,
            messages=messages,
            temperature=model_profile.temperature,
            max_tokens=model_profile.max_tokens,
        )
        usage = response.usage
        return LLMResponse(
            content=(response.choices[0].message.content or "").strip(),
            usage=AgentRunUsage(
                requests=1,
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            ),
            model_name=response.model,
        )

    async def generate_text_stream(
        self,
        prompt: str,
        *,
        profile: str = "chat",
        system: str = "",
        on_delta=None,
    ) -> LLMResponse:
        """Stream a completion; awaits `on_delta(text)` per chunk, returns the
        final accumulated response with usage."""

        model_profile = self._profile(profile)
        client = self._ensure_client(model_profile)
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        stream = await client.chat.completions.create(
            model=model_profile.model or DEFAULT_MODEL,
            messages=messages,
            temperature=model_profile.temperature,
            max_tokens=model_profile.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        parts: list[str] = []
        usage = AgentRunUsage(requests=1)
        model_name = model_profile.model or DEFAULT_MODEL
        async for chunk in stream:
            if getattr(chunk, "model", None):
                model_name = chunk.model
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                parts.append(delta)
                if on_delta is not None:
                    await on_delta(delta)
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = AgentRunUsage(
                    requests=1,
                    input_tokens=getattr(chunk_usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(chunk_usage, "completion_tokens", 0) or 0,
                    total_tokens=getattr(chunk_usage, "total_tokens", 0) or 0,
                )
        return LLMResponse(
            content="".join(parts).strip(),
            usage=usage,
            model_name=model_name,
        )

    async def generate_json(
        self,
        prompt: str,
        *,
        profile: str = "chat",
        system: str = "",
    ) -> LLMResponse:
        import json

        model_profile = self._profile(profile)
        client = self._ensure_client(model_profile)
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await client.chat.completions.create(
            model=model_profile.model or DEFAULT_MODEL,
            messages=messages,
            temperature=model_profile.temperature,
            max_tokens=model_profile.max_tokens,
            response_format={"type": "json_object"},
        )
        content = (response.choices[0].message.content or "{}").strip()
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            data = {}
        usage = response.usage
        return LLMResponse(
            content=content,
            data=data,
            usage=AgentRunUsage(
                requests=1,
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            ),
            model_name=response.model,
        )
