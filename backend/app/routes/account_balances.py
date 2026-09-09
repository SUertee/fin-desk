"""API for point-in-time balances confirmed by the user."""

from fastapi import APIRouter

from app.models.account_balances import AccountBalancesUpdate
from app.services.account_balances import confirm_account_balances, get_account_balances

router = APIRouter(prefix="/account-balances", tags=["account-balances"])


@router.get("/{user_id}")
def read_account_balances(user_id: str):
    return get_account_balances(user_id).model_dump(mode="json")


@router.put("/{user_id}")
def write_account_balances(user_id: str, req: AccountBalancesUpdate):
    return confirm_account_balances(user_id, req).model_dump(mode="json")
