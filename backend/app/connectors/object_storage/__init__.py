"""Provider-neutral object storage connectors."""

from app.connectors.object_storage.minio_provider import (
    MinioObjectStorageProvider,
)

__all__ = ["MinioObjectStorageProvider"]
