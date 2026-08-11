"""Typed vision-language connector failures."""


class VisionError(RuntimeError):
    """Base error for vision-language operations."""


class VisionProviderError(VisionError):
    """Stable error boundary for provider failures (no credentials or bodies)."""


class VisionConfigError(VisionError):
    """Raised when required vision settings are missing or invalid."""
