"""Stable errors raised by market-data connectors and services."""


class MarketDataError(RuntimeError):
    """Base class for non-secret market-data failures."""


class MarketDataUnavailable(MarketDataError):
    pass


class MarketDataProviderError(MarketDataError):
    pass


class MarketDataTimeout(MarketDataProviderError):
    pass


class MarketDataBudgetExceeded(MarketDataError):
    pass
