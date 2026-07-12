"""DeepSeek client: per-profile client cache.

Profiles differ in timeout (router fails fast at 10s) and may differ in
key env / base URL; the adapter must never let the first caller's profile
settings leak into other profiles through a shared client.
"""

import openai

from app.config.settings import ModelProfile
from app.runtime.llm.deepseek_client import DeepSeekTextClient


class FakeAsyncOpenAI:
    def __init__(self, *, api_key="", base_url="", timeout=None):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout


def _client_with_two_profiles(monkeypatch):
    monkeypatch.setattr(openai, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    profiles = {
        "chat": ModelProfile(name="chat", timeout_seconds=30),
        "router": ModelProfile(name="router", timeout_seconds=10),
    }
    return DeepSeekTextClient(profiles=profiles), profiles


def test_each_profile_gets_its_own_client(monkeypatch):
    client, profiles = _client_with_two_profiles(monkeypatch)

    chat = client._ensure_client("chat", profiles["chat"])
    router = client._ensure_client("router", profiles["router"])

    assert chat is not router
    assert chat.timeout == 30
    # The router's fast-fail timeout must not leak into the chat client
    # (and vice versa), regardless of which profile is created first.
    assert router.timeout == 10


def test_profile_client_is_cached_per_profile(monkeypatch):
    client, profiles = _client_with_two_profiles(monkeypatch)

    first = client._ensure_client("router", profiles["router"])
    second = client._ensure_client("router", profiles["router"])
    other = client._ensure_client("chat", profiles["chat"])

    assert first is second
    assert other is not first
    assert set(client._clients) == {"router", "chat"}
