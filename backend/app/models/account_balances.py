"""Models for user-confirmed point-in-time account balances."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AccountType = Literal["bank", "alipay", "wechat", "cash"]


class AccountBalanceItem(BaseModel):
    account_type: AccountType
    amount: float = Field(ge=0)
    currency: str = "CNY"
    confirmed_at: datetime


class AccountBalancesUpdate(BaseModel):
    bank: float = Field(default=0, ge=0, le=100_000_000)
    alipay: float = Field(default=0, ge=0, le=100_000_000)
    wechat: float = Field(default=0, ge=0, le=100_000_000)
    cash: float = Field(default=0, ge=0, le=100_000_000)
    currency: str = Field(default="CNY", min_length=3, max_length=3)


class AccountBalancesResponse(BaseModel):
    user_id: str
    currency: str
    items: list[AccountBalanceItem]
    total: float
    confirmed_at: datetime | None = None
