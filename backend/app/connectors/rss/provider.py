"""Provider-neutral RSS connector protocol."""

from __future__ import annotations

from typing import Protocol

from app.models.finance_inbox import FeedDocument
from app.models.subscriptions import ContentSubscription


class RSSProvider(Protocol):
    def fetch(self, subscription: ContentSubscription) -> FeedDocument: ...
