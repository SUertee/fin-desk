"""Bounded HTTP RSS/Atom provider backed by feedparser."""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import feedparser
import httpx
from defusedxml import ElementTree

from app.connectors.rss.errors import RSSConnectorError
from app.connectors.rss.security import (
    AddressResolver,
    validate_article_url,
    validate_external_feed_url,
)
from app.models.finance_inbox import FeedDocument, NormalizedFeedEntry
from app.models.subscriptions import ContentSubscription


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "template"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def _plain_text(value: Any, limit: int) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(str(value or ""))
    except Exception:
        return ""
    return " ".join(" ".join(parser.parts).split())[:limit]


def _published_at(entry: Any) -> datetime | None:
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(field)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


class FeedparserRSSProvider:
    def __init__(
        self,
        *,
        timeout_seconds: int = 10,
        max_response_bytes: int = 2_000_000,
        max_entries: int = 200,
        max_redirects: int = 3,
        allow_proxy_fake_ips: bool = False,
        resolver: AddressResolver | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_entries = max_entries
        self.max_redirects = max_redirects
        self.allow_proxy_fake_ips = allow_proxy_fake_ips
        self.resolver = resolver
        self.transport = transport

    def fetch(self, subscription: ContentSubscription) -> FeedDocument:
        current_url = subscription.normalized_feed_url
        headers = {
            "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
            "User-Agent": "FinDesk-Finance-Inbox/0.1",
        }
        if subscription.etag:
            headers["If-None-Match"] = subscription.etag
        if subscription.last_modified:
            headers["If-Modified-Since"] = subscription.last_modified
        fetched_at = datetime.now(timezone.utc)
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                for redirect_count in range(self.max_redirects + 1):
                    current_url = validate_external_feed_url(
                        current_url,
                        resolver=self.resolver,
                        allow_proxy_fake_ips=self.allow_proxy_fake_ips,
                    )
                    with client.stream("GET", current_url, headers=headers) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect_count >= self.max_redirects:
                                raise RSSConnectorError("redirect_limit")
                            location = response.headers.get("location")
                            if not location:
                                raise RSSConnectorError("invalid_redirect")
                            current_url = urljoin(current_url, location)
                            continue
                        if response.status_code == 304:
                            return FeedDocument(
                                feed_url=subscription.normalized_feed_url,
                                final_url=current_url,
                                fetched_at=fetched_at,
                                not_modified=True,
                                etag=response.headers.get("etag") or subscription.etag,
                                last_modified=(
                                    response.headers.get("last-modified")
                                    or subscription.last_modified
                                ),
                            )
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").lower()
                        if content_type and not any(
                            token in content_type
                            for token in ("xml", "rss", "atom", "text/plain")
                        ):
                            raise RSSConnectorError("unsupported_feed")
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            body.extend(chunk)
                            if len(body) > self.max_response_bytes:
                                raise RSSConnectorError("response_too_large")
                        return self._parse(
                            bytes(body),
                            subscription=subscription,
                            final_url=current_url,
                            fetched_at=fetched_at,
                            etag=response.headers.get("etag"),
                            last_modified=response.headers.get("last-modified"),
                        )
        except RSSConnectorError:
            raise
        except httpx.TimeoutException as exc:
            raise RSSConnectorError("fetch_timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise RSSConnectorError("fetch_http_error") from exc
        except httpx.HTTPError as exc:
            raise RSSConnectorError("provider_unavailable") from exc
        raise RSSConnectorError("provider_unavailable")

    def _parse(
        self,
        payload: bytes,
        *,
        subscription: ContentSubscription,
        final_url: str,
        fetched_at: datetime,
        etag: str | None,
        last_modified: str | None,
    ) -> FeedDocument:
        try:
            ElementTree.fromstring(payload)
        except Exception as exc:
            raise RSSConnectorError("malformed_feed") from exc
        parsed = feedparser.parse(payload)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise RSSConnectorError("malformed_feed")
        entries: list[NormalizedFeedEntry] = []
        invalid_count = 0
        for raw in parsed.entries[: self.max_entries]:
            title = _plain_text(raw.get("title"), 500)
            url = validate_article_url(urljoin(final_url, raw.get("link", "")))
            entry_id = _plain_text(raw.get("id") or raw.get("guid"), 500) or None
            if not title or (not url and not entry_id):
                invalid_count += 1
                continue
            content = raw.get("summary") or raw.get("description") or ""
            if not content and raw.get("content"):
                content = raw.get("content")[0].get("value", "")
            entries.append(
                NormalizedFeedEntry(
                    title=title,
                    url=url,
                    excerpt=_plain_text(content, 2000),
                    author=_plain_text(raw.get("author"), 200) or None,
                    published_at=_published_at(raw),
                    feed_entry_id=entry_id,
                )
            )
        return FeedDocument(
            feed_url=subscription.normalized_feed_url,
            final_url=final_url,
            feed_title=_plain_text(parsed.feed.get("title"), 500),
            fetched_at=fetched_at,
            entries=entries,
            invalid_count=invalid_count,
            etag=etag,
            last_modified=last_modified,
        )
