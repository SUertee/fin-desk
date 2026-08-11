"""Typed object-storage connector failures."""


class ObjectStorageError(RuntimeError):
    """Base error for object-storage operations."""


class ObjectStorageProviderError(ObjectStorageError):
    """Raised when the storage backend rejects or fails an operation."""


class ObjectStorageConfigError(ObjectStorageError):
    """Raised when required storage settings are missing or invalid."""
