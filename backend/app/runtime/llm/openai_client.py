"""OpenAI provider adapter placeholder.

The default self-hosted runtime does not use this module for orchestration. It
exists so future LLM-backed steps have a narrow provider boundary.
"""

from __future__ import annotations

from app.runtime.llm.client import LLMResponse


class OpenAITextClient:
    async def generate_text(self, prompt: str, *, profile: str = "chat") -> LLMResponse:
        raise NotImplementedError("OpenAI text generation is not wired in this slice")

    async def generate_json(self, prompt: str, *, profile: str = "chat") -> LLMResponse:
        raise NotImplementedError("OpenAI JSON generation is not wired in this slice")
