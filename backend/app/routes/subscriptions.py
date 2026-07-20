"""Finance content subscription management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config.settings import get_settings
from app.connectors.postgres.subscription_store import (
    SubscriptionStoreUnavailable,
    create_or_get_subscription_db,
    list_subscriptions_db,
    update_subscription_db,
)
from app.connectors.rss.security import validate_external_feed_url
from app.models.subscriptions import (
    ContentSubscription,
    ContentSubscriptionCreate,
    ContentSubscriptionUpdate,
    OPMLImportResult,
    SubscriptionCreateResult,
)
from app.services.inbox_errors import FinanceInboxError
from app.services.subscriptions import SubscriptionService


router = APIRouter(prefix="/inbox/{user_id}/subscriptions", tags=["finance-inbox"])
_settings = get_settings().finance_inbox
_service = SubscriptionService(
    create_or_get=create_or_get_subscription_db,
    list_subscriptions=list_subscriptions_db,
    update_subscription=update_subscription_db,
    url_validator=lambda value: validate_external_feed_url(
        value,
        allow_proxy_fake_ips=_settings.allow_proxy_fake_ips,
    ),
    max_opml_bytes=_settings.max_opml_bytes,
    max_opml_outlines=_settings.max_opml_outlines,
)


def _raise_http(exc: FinanceInboxError) -> None:
    status = 404 if exc.code == "not_found" else 400
    raise HTTPException(status_code=status, detail={"code": exc.code}) from exc


def _raise_unavailable(exc: RuntimeError) -> None:
    raise HTTPException(
        status_code=503,
        detail={"code": "finance_inbox_unavailable"},
    ) from exc


@router.post("", response_model=SubscriptionCreateResult)
def create_subscription(
    user_id: str,
    payload: ContentSubscriptionCreate,
) -> SubscriptionCreateResult:
    try:
        return _service.create(user_id, payload)
    except FinanceInboxError as exc:
        _raise_http(exc)
    except SubscriptionStoreUnavailable as exc:
        _raise_unavailable(exc)


@router.get("", response_model=list[ContentSubscription])
def list_subscriptions(user_id: str) -> list[ContentSubscription]:
    try:
        return _service.list(user_id)
    except SubscriptionStoreUnavailable as exc:
        _raise_unavailable(exc)


@router.patch("/{subscription_id}", response_model=ContentSubscription)
def update_subscription(
    user_id: str,
    subscription_id: str,
    payload: ContentSubscriptionUpdate,
) -> ContentSubscription:
    try:
        return _service.update(user_id, subscription_id, payload)
    except FinanceInboxError as exc:
        _raise_http(exc)
    except SubscriptionStoreUnavailable as exc:
        _raise_unavailable(exc)


@router.post("/import-opml", response_model=OPMLImportResult)
async def import_opml(
    user_id: str,
    file: UploadFile = File(...),
) -> OPMLImportResult:
    payload = await file.read(_settings.max_opml_bytes + 1)
    try:
        return _service.import_opml(user_id, payload)
    except FinanceInboxError as exc:
        _raise_http(exc)
    except SubscriptionStoreUnavailable as exc:
        _raise_unavailable(exc)
