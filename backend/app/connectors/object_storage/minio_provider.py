"""MinIO (S3-compatible) object storage adapter.

Originals and thumbnails live in one private bucket. Presigned GET URLs are
issued via an externally reachable endpoint (``external_endpoint``) so the
browser can load them even when the backend resolves MinIO through the
docker-internal hostname. If ``external_endpoint`` is empty the same client is
used for both operations and presigning (local-dev mode where the backend
itself reaches MinIO via ``localhost``).
"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from minio import Minio

from app.connectors.object_storage.errors import ObjectStorageProviderError


class MinioObjectStorageProvider:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        external_endpoint: str = "",
        external_secure: bool = False,
        presign_ttl_seconds: int = 300,
        client: Minio | None = None,
        presign_client: Minio | None = None,
        auto_create_bucket: bool = True,
    ) -> None:
        if not endpoint.strip():
            raise ValueError("minio endpoint is required")
        if not bucket.strip():
            raise ValueError("minio bucket is required")
        self.bucket = bucket
        self.presign_ttl_seconds = presign_ttl_seconds
        self._client = client if client is not None else Minio(
            endpoint, access_key=access_key, secret_key=secret_key, secure=secure
        )
        if presign_client is not None:
            self._presign_client = presign_client
        elif external_endpoint:
            self._presign_client = Minio(
                external_endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=external_secure,
            )
        else:
            self._presign_client = self._client
        if auto_create_bucket:
            try:
                if not self._client.bucket_exists(bucket):
                    self._client.make_bucket(bucket)
            except Exception as exc:
                raise ObjectStorageProviderError(
                    f"minio bucket '{bucket}' unavailable"
                ) from exc

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                self.bucket,
                key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        except Exception as exc:
            raise ObjectStorageProviderError(
                f"minio put_object failed for key '{key}'"
            ) from exc

    def get_object(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(self.bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        except Exception as exc:
            raise ObjectStorageProviderError(
                f"minio get_object failed for key '{key}'"
            ) from exc

    def get_presigned_url(self, key: str, *, expires_seconds: int | None = None) -> str:
        expires = timedelta(seconds=expires_seconds or self.presign_ttl_seconds)
        try:
            return self._presign_client.presigned_get_object(
                self.bucket, key, expires=expires
            )
        except Exception as exc:
            raise ObjectStorageProviderError(
                f"minio presign failed for key '{key}'"
            ) from exc

    def delete_object(self, key: str) -> None:
        try:
            self._client.remove_object(self.bucket, key)
        except Exception as exc:
            raise ObjectStorageProviderError(
                f"minio delete_object failed for key '{key}'"
            ) from exc
