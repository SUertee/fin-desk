"""SSRF-resistant URL normalization and destination validation."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import SplitResult, urlsplit, urlunsplit

from app.connectors.rss.errors import RSSConnectorError


AddressResolver = Callable[[str, int], Iterable[str]]
ALLOWED_PORTS = {80, 443}
_PROXY_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def _default_resolver(host: str, port: int) -> list[str]:
    try:
        return list(
            dict.fromkeys(
                item[4][0]
                for item in socket.getaddrinfo(
                    host,
                    port,
                    type=socket.SOCK_STREAM,
                )
            )
        )
    except socket.gaierror as exc:
        raise RSSConnectorError("dns_resolution_failed") from exc


def normalize_feed_url(value: str) -> str:
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise RSSConnectorError("invalid_url") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise RSSConnectorError("invalid_url")
    if parsed.username or parsed.password:
        raise RSSConnectorError("unsafe_url")
    selected_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    if selected_port not in ALLOWED_PORTS:
        raise RSSConnectorError("unsafe_port")
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    if not host:
        raise RSSConnectorError("invalid_url")
    netloc = host
    if port and not (
        (parsed.scheme.lower() == "https" and port == 443)
        or (parsed.scheme.lower() == "http" and port == 80)
    ):
        netloc = f"{host}:{port}"
    normalized = SplitResult(
        scheme=parsed.scheme.lower(),
        netloc=netloc,
        path=parsed.path or "/",
        query=parsed.query,
        fragment="",
    )
    return urlunsplit(normalized)


def _is_public_address(raw: str) -> bool:
    try:
        address = ipaddress.ip_address(raw.split("%")[0])
    except ValueError:
        return False
    return address.is_global


def _is_proxy_fake_address(raw: str) -> bool:
    try:
        return ipaddress.ip_address(raw.split("%")[0]) in _PROXY_FAKE_IP_NETWORK
    except ValueError:
        return False


def validate_external_feed_url(
    value: str,
    *,
    resolver: AddressResolver | None = None,
    allow_proxy_fake_ips: bool = False,
) -> str:
    normalized = normalize_feed_url(value)
    parsed = urlsplit(normalized)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
        allowed = all(_is_public_address(item) for item in addresses)
    else:
        addresses = list((resolver or _default_resolver)(host, port))
        allowed = all(
            _is_public_address(item)
            or (allow_proxy_fake_ips and _is_proxy_fake_address(item))
            for item in addresses
        )
    if not addresses or not allowed:
        raise RSSConnectorError("unsafe_url")
    return normalized


def validate_article_url(value: str) -> str | None:
    try:
        normalized = normalize_feed_url(value)
        host = urlsplit(normalized).hostname or ""
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return normalized
        return normalized if address.is_global else None
    except RSSConnectorError:
        return None
