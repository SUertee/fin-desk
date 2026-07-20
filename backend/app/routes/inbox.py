"""Manual refresh and read APIs for Finance Inbox."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.config.settings import get_settings
from app.connectors.postgres.inbox_store import (
    InboxStoreUnavailable,
    get_inbox_summary_db,
    list_inbox_items_db,
    update_inbox_item_status_db,
    upsert_inbox_items_db,
)
from app.connectors.postgres.subscription_store import (
    SubscriptionStoreUnavailable,
    get_subscription_db,
    list_subscriptions_db,
    update_subscription_refresh_db,
)
from app.connectors.rss import FeedparserRSSProvider
from app.models.finance_inbox import (
    InboxItem,
    InboxItemStatusUpdate,
    InboxPage,
    InboxSummary,
)
from app.models.subscriptions import RefreshAllResult, RefreshResult
from app.services.inbox_errors import FinanceInboxError
from app.services.inbox_ingestion import InboxIngestionService
from app.services.inbox_query import InboxQueryService


router = APIRouter(prefix="/inbox/{user_id}", tags=["finance-inbox"])
_settings = get_settings().finance_inbox
_ingestion = InboxIngestionService(
    provider=FeedparserRSSProvider(
        timeout_seconds=_settings.timeout_seconds,
        max_response_bytes=_settings.max_response_bytes,
        max_entries=_settings.max_entries_per_feed,
        max_redirects=_settings.max_redirects,
        allow_proxy_fake_ips=_settings.allow_proxy_fake_ips,
    ),
    get_subscription=get_subscription_db,
    list_subscriptions=list_subscriptions_db,
    upsert_items=upsert_inbox_items_db,
    update_refresh=update_subscription_refresh_db,
)
_query = InboxQueryService(
    list_items=list_inbox_items_db,
    update_status=update_inbox_item_status_db,
    get_summary=get_inbox_summary_db,
)


def _raise_http(exc: FinanceInboxError) -> None:
    status = 404 if exc.code == "not_found" else 400
    raise HTTPException(status_code=status, detail={"code": exc.code}) from exc


def _raise_unavailable(exc: RuntimeError) -> None:
    raise HTTPException(
        status_code=503,
        detail={"code": "finance_inbox_unavailable"},
    ) from exc


@router.post("/subscriptions/{subscription_id}/refresh", response_model=RefreshResult)
def refresh_subscription(user_id: str, subscription_id: str) -> RefreshResult:
    try:
        return _ingestion.refresh_one(user_id, subscription_id)
    except FinanceInboxError as exc:
        _raise_http(exc)
    except (InboxStoreUnavailable, SubscriptionStoreUnavailable) as exc:
        _raise_unavailable(exc)


@router.post("/refresh", response_model=RefreshAllResult)
def refresh_all(user_id: str) -> RefreshAllResult:
    try:
        return _ingestion.refresh_all(user_id)
    except (InboxStoreUnavailable, SubscriptionStoreUnavailable) as exc:
        _raise_unavailable(exc)


@router.get("/summary", response_model=InboxSummary)
def get_summary(user_id: str) -> InboxSummary:
    try:
        return _query.summary(user_id)
    except InboxStoreUnavailable as exc:
        _raise_unavailable(exc)


@router.get("/items", response_model=InboxPage)
def list_items(
    user_id: str,
    status: Literal["unread", "read", "saved", "dismissed"] | None = Query(
        default=None
    ),
    limit: int = Query(default=30, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1000),
) -> InboxPage:
    try:
        return _query.list(
            user_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
    except FinanceInboxError as exc:
        _raise_http(exc)
    except InboxStoreUnavailable as exc:
        _raise_unavailable(exc)


@router.patch("/items/{item_id}", response_model=InboxItem)
def update_item_status(
    user_id: str,
    item_id: str,
    payload: InboxItemStatusUpdate,
) -> InboxItem:
    try:
        return _query.update_status(user_id, item_id, payload.status)
    except FinanceInboxError as exc:
        _raise_http(exc)
    except InboxStoreUnavailable as exc:
        _raise_unavailable(exc)
