"""Fail-open Redis JSON cache.

PostgreSQL remains the durable source of truth. Redis entries are disposable,
TTL-bounded projections used to share hot memory across backend workers.
"""

from __future__ import annotations

import json
import logging
from hashlib import sha256
from typing import Any, Iterable

from app.config.settings import RedisSettings, get_settings

logger = logging.getLogger(__name__)


def cache_scope(value: str) -> str:
    """Keep user and session identifiers out of cache keys."""

    return sha256(value.encode("utf-8")).hexdigest()[:20]


class RedisJsonCache:
    def __init__(self, settings: RedisSettings, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client or self._create_client(settings)

    @staticmethod
    def _create_client(settings: RedisSettings) -> Any:
        from redis import Redis

        return Redis.from_url(
            settings.url,
            decode_responses=True,
            socket_connect_timeout=settings.socket_timeout_seconds,
            socket_timeout=settings.socket_timeout_seconds,
            health_check_interval=30,
        )

    def key(self, namespace: str, *parts: str) -> str:
        scopes = ":".join(cache_scope(part) for part in parts)
        return f"{self.settings.key_prefix}:{namespace}:{scopes}"

    def get_json(self, key: str) -> Any | None:
        try:
            raw = self._client.get(key)
            return None if raw is None else json.loads(raw)
        except Exception as exc:
            logger.warning("Redis cache read failed: %s", exc)
            return None

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> bool:
        try:
            self._client.set(
                key,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=ttl_seconds,
            )
            return True
        except Exception as exc:
            logger.warning("Redis cache write failed: %s", exc)
            return False

    def delete(self, *keys: str) -> bool:
        if not keys:
            return True
        try:
            self._client.delete(*keys)
            return True
        except Exception as exc:
            logger.warning("Redis cache invalidation failed: %s", exc)
            return False

    def delete_matching(self, pattern: str) -> bool:
        try:
            keys: Iterable[str] = self._client.scan_iter(match=pattern, count=100)
            batch = list(keys)
            if batch:
                self._client.delete(*batch)
            return True
        except Exception as exc:
            logger.warning("Redis cache pattern invalidation failed: %s", exc)
            return False

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            logger.debug("Redis cache close failed", exc_info=True)


_cache: RedisJsonCache | None = None


def get_redis_cache() -> RedisJsonCache | None:
    global _cache
    settings = get_settings().redis
    if not settings.enabled:
        return None
    if _cache is None:
        _cache = RedisJsonCache(settings)
    return _cache


def close_redis_cache() -> None:
    global _cache
    if _cache is not None:
        _cache.close()
        _cache = None


def redis_cache_status() -> str:
    cache = get_redis_cache()
    if cache is None:
        return "disabled"
    return "ok" if cache.ping() else "unavailable"
