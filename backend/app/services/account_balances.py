"""Account balance confirmation and cash-plan synchronization."""

from datetime import datetime, timezone

from app.connectors.postgres.account_balances_store import (
    get_account_balances_db,
    save_account_balances_db,
)
from app.models.account_balances import (
    AccountBalanceItem,
    AccountBalancesResponse,
    AccountBalancesUpdate,
)
from app.services.cash_plan import update_cash_balance

ACCOUNT_TYPES = ("bank", "alipay", "wechat", "cash")
_cache: dict[str, AccountBalancesResponse] = {}


def get_account_balances(user_id: str) -> AccountBalancesResponse:
    if user_id in _cache:
        return _cache[user_id]
    items = get_account_balances_db(user_id)
    response = _response(user_id, items)
    if items:
        _cache[user_id] = response
    return response


def confirm_account_balances(
    user_id: str, req: AccountBalancesUpdate
) -> AccountBalancesResponse:
    confirmed_at = datetime.now(timezone.utc)
    currency = req.currency.upper()
    items = [
        AccountBalanceItem(
            account_type=account_type,
            amount=getattr(req, account_type),
            currency=currency,
            confirmed_at=confirmed_at,
        )
        for account_type in ACCOUNT_TYPES
    ]
    response = _response(user_id, items)
    _cache[user_id] = response
    save_account_balances_db(user_id, items, confirmed_at)
    update_cash_balance(user_id, response.total, currency=currency)
    return response


def _response(user_id: str, items: list[AccountBalanceItem]) -> AccountBalancesResponse:
    confirmed_at = max((item.confirmed_at for item in items), default=None)
    currency = items[0].currency if items else "CNY"
    return AccountBalancesResponse(
        user_id=user_id,
        currency=currency,
        items=items,
        total=round(sum(item.amount for item in items), 2),
        confirmed_at=confirmed_at,
    )
