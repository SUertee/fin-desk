from datetime import datetime, timezone

import httpx
import pytest

from app.connectors.rss.errors import RSSConnectorError
from app.connectors.rss.feedparser_provider import FeedparserRSSProvider
from app.connectors.rss.opml import parse_opml
from app.connectors.rss.security import (
    normalize_feed_url,
    validate_article_url,
    validate_external_feed_url,
)
from app.models.subscriptions import ContentSubscription


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def subscription(url: str = "https://example.com/feed.xml") -> ContentSubscription:
    return ContentSubscription(
        id="subscription-1",
        user_id="demo",
        name="Example Feed",
        feed_url=url,
        normalized_feed_url=url,
        created_at=NOW,
        updated_at=NOW,
    )


def public_resolver(host: str, port: int):
    return ["93.184.216.34"]


def test_normalize_feed_url_removes_fragment_and_default_port():
    assert normalize_feed_url("HTTPS://Example.COM:443/feed#latest") == (
        "https://example.com/feed"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/feed",
        "http://10.0.0.2/feed",
        "http://169.254.169.254/latest/meta-data",
        "file:///tmp/feed.xml",
        "https://user:password@example.com/feed",
        "https://example.com:8443/feed",
    ],
)
def test_validate_external_feed_url_rejects_unsafe_destinations(url):
    with pytest.raises(RSSConnectorError):
        validate_external_feed_url(url, resolver=public_resolver)


def test_proxy_fake_ip_mode_allows_hostname_but_not_literal_ip():
    assert validate_external_feed_url(
        "https://feeds.example.com/rss.xml",
        resolver=lambda host, port: ["198.18.0.42"],
        allow_proxy_fake_ips=True,
    ) == "https://feeds.example.com/rss.xml"

    with pytest.raises(RSSConnectorError):
        validate_external_feed_url(
            "http://198.18.0.42/feed.xml",
            resolver=lambda host, port: ["198.18.0.42"],
            allow_proxy_fake_ips=True,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://service.local/private",
        "http://127.0.0.1/debug",
    ],
)
def test_article_links_reject_local_destinations(url):
    assert validate_article_url(url) is None


def test_provider_parses_and_sanitizes_rss_entries():
    payload = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Finance Daily</title>
      <item><title>Rates &amp; Markets</title>
        <link>https://example.com/article?utm_source=rss</link>
        <guid>article-1</guid>
        <description><![CDATA[<b>Central bank</b> update<script>bad()</script>]]></description>
        <pubDate>Sun, 20 Jul 2026 08:00:00 GMT</pubDate>
      </item>
    </channel></rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/rss+xml", "etag": "v1"},
            content=payload,
        )

    provider = FeedparserRSSProvider(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    result = provider.fetch(subscription())

    assert result.feed_title == "Finance Daily"
    assert result.etag == "v1"
    assert len(result.entries) == 1
    assert result.entries[0].title == "Rates & Markets"
    assert result.entries[0].excerpt == "Central bank update"
    assert "<script>" not in result.entries[0].excerpt


def test_provider_revalidates_redirect_destination():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/feed"})

    provider = FeedparserRSSProvider(
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RSSConnectorError) as raised:
        provider.fetch(subscription())

    assert raised.value.code == "unsafe_url"
    assert requests == ["https://example.com/feed.xml"]


def test_provider_stops_when_response_is_too_large():
    provider = FeedparserRSSProvider(
        max_response_bytes=20,
        resolver=public_resolver,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                content=b"<rss><channel>too much content</channel></rss>",
            )
        ),
    )

    with pytest.raises(RSSConnectorError) as raised:
        provider.fetch(subscription())

    assert raised.value.code == "response_too_large"


def test_provider_rejects_external_entity_xml():
    payload = b'''<?xml version="1.0"?>
    <!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <rss><channel><title>&xxe;</title></channel></rss>'''
    provider = FeedparserRSSProvider(
        resolver=public_resolver,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                content=payload,
            )
        ),
    )

    with pytest.raises(RSSConnectorError) as raised:
        provider.fetch(subscription())

    assert raised.value.code == "malformed_feed"


def test_opml_parser_is_bounded_and_extracts_feed_names():
    payload = b'''<?xml version="1.0"?>
    <opml version="2.0"><body>
      <outline text="Finance">
        <outline title="Central Banks" xmlUrl="https://example.com/banks.xml" />
      </outline>
    </body></opml>'''

    feeds = parse_opml(payload, max_bytes=1000, max_outlines=10)

    assert [(item.name, item.feed_url) for item in feeds] == [
        ("Central Banks", "https://example.com/banks.xml")
    ]


def test_opml_parser_rejects_outline_overflow():
    payload = b'''<opml><body>
      <outline text="One" xmlUrl="https://example.com/one.xml" />
      <outline text="Two" xmlUrl="https://example.com/two.xml" />
    </body></opml>'''

    with pytest.raises(RSSConnectorError) as raised:
        parse_opml(payload, max_bytes=1000, max_outlines=1)

    assert raised.value.code == "opml_outline_limit"
