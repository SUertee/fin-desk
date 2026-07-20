"""Typed web-search connector failures."""


class WebSearchError(RuntimeError):
    """Base class for governed web-search failures."""


class WebSearchNotConfigured(WebSearchError):
    """The selected provider cannot be called in this deployment."""


class WebSearchProviderError(WebSearchError):
    """The provider failed or returned an unusable response."""


class WebSearchBudgetExceeded(WebSearchError):
    """The per-run external-call budget is exhausted."""
