"""Object storage provider protocol.

Implementations store user-uploaded document originals and image thumbnails in
a private bucket and issue short-lived presigned GET URLs for browser preview.
The protocol is intentionally minimal: the ingestion service only needs put /
get / delete plus presign. ``key`` is always a content-addressed suffix (e.g.
``users/{uid}/documents/{doc_id}/images/{hash}.png``); the bucket name is held
by the implementation, not the caller.
"""

from __future__ import annotations

from typing import Protocol


class ObjectStorageProvider(Protocol):
    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        """Upload ``data`` under ``key``."""

    def get_object(self, key: str) -> bytes:
        """Download the bytes stored under ``key``."""

    def get_presigned_url(self, key: str, *, expires_seconds: int | None = None) -> str:
        """Return a short-lived GET URL a browser can load ``key`` from."""

    def delete_object(self, key: str) -> None:
        """Remove the object under ``key``."""
