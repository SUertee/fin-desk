"""Bounded Finance Inbox reads and state transitions."""

from __future__ import annotations

import base64
import json
from datetime import datetime

from app.models.finance_inbox import InboxItem, InboxPage, InboxSummary
from app.services.inbox_errors import FinanceInboxError


def _encode_cursor(created_at: datetime, item_id: str) -> str:
    raw = json.dumps(
        {"created_at": created_at.isoformat(), "id": item_id},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(value: str | None) -> tuple[datetime | None, str | None]:
    if not value:
        return None, None
    try:
        payload = json.loads(base64.urlsafe_b64decode(value.encode("ascii")))
        created_at = datetime.fromisoformat(payload["created_at"])
        item_id = str(payload["id"])
        if created_at.tzinfo is None or created_at.utcoffset() is None or not item_id:
            raise ValueError
        return created_at, item_id
    except Exception as exc:
        raise FinanceInboxError("invalid_cursor") from exc


class InboxQueryService:
    def __init__(self, *, list_items, update_status, get_summary) -> None:
        self.list_reader = list_items
        self.status_writer = update_status
        self.summary_reader = get_summary

    def list(
        self,
        user_id: str,
        *,
        status: str | None,
        limit: int,
        cursor: str | None,
    ) -> InboxPage:
        before_created_at, before_id = _decode_cursor(cursor)
        items, has_more = self.list_reader(
            user_id,
            status=status,
            limit=min(max(limit, 1), 50),
            before_created_at=before_created_at,
            before_id=before_id,
        )
        next_cursor = (
            _encode_cursor(items[-1].created_at, items[-1].id)
            if has_more and items
            else None
        )
        return InboxPage(items=items, next_cursor=next_cursor)

    def update_status(self, user_id: str, item_id: str, status: str) -> InboxItem:
        updated = self.status_writer(user_id, item_id, status)
        if updated is None:
            raise FinanceInboxError("not_found")
        return updated

    def summary(self, user_id: str) -> InboxSummary:
        return self.summary_reader(user_id)
