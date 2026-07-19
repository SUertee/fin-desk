"""Typed exchange-rate connector failures."""


class ExchangeRateError(RuntimeError):
    """Base error for exchange-rate retrieval."""


class ExchangeRateUnavailable(ExchangeRateError):
    """Raised when no persisted or provider rate is available."""


class ExchangeRateProviderError(ExchangeRateError):
    """Raised when a provider response is invalid or unavailable."""
