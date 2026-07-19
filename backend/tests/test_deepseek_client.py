"""DeepSeek client: per-profile client cache.

Profiles differ in timeout (router fails fast at 10s) and may differ in
key env / base URL; the adapter must never let the first caller's profile
settings leak into other profiles through a shared client.
"""

from types import SimpleNamespace

import openai

from app.config.settings import ModelProfile, load_model_profiles
from app.runtime.llm.deepseek_client import DeepSeekTextClient
from app.runtime.llm.usage import usage_from_response


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


def test_deepseek_profile_uses_current_direct_model_and_official_price_snapshot():
    load_model_profiles.cache_clear()
    profile = load_model_profiles()["chat"]

    assert profile.model == "deepseek-v4-flash"
    assert str(profile.input_cost_per_1m) == "0.14"
    assert str(profile.cached_input_cost_per_1m) == "0.0028"
    assert str(profile.output_cost_per_1m) == "0.28"
    assert profile.pricing_source == "deepseek_official_pricing"


def test_v4_requests_explicitly_disable_thinking():
    assert DeepSeekTextClient._completion_options("deepseek-v4-flash") == {
        "extra_body": {"thinking": {"type": "disabled"}}
    }
    assert DeepSeekTextClient._completion_options("legacy-model") == {}


def test_deepseek_cache_usage_is_normalized_to_provider_neutral_fields():
    usage = usage_from_response(
        SimpleNamespace(
            prompt_tokens=1000,
            prompt_cache_hit_tokens=700,
            prompt_cache_miss_tokens=300,
            completion_tokens=100,
            total_tokens=1100,
        )
    )

    assert usage.input_tokens == 1000
    assert usage.cached_input_tokens == 700
    assert usage.uncached_input_tokens == 300
    assert usage.output_tokens == 100
    assert usage.total_tokens == 1100


def test_openai_style_cached_tokens_are_normalized():
    usage = usage_from_response(
        SimpleNamespace(
            prompt_tokens=1000,
            prompt_tokens_details=SimpleNamespace(cached_tokens=250),
            completion_tokens=100,
            total_tokens=1100,
        )
    )

    assert usage.cached_input_tokens == 250
    assert usage.uncached_input_tokens == 750
