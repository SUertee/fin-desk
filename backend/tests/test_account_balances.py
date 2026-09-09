from app.models.account_balances import AccountBalancesUpdate
from app.services import account_balances as service


def test_confirming_balances_sums_accounts_and_updates_projection_baseline(monkeypatch):
    saved = {}
    monkeypatch.setattr(service, "save_account_balances_db", lambda user_id, items, confirmed_at: True)
    monkeypatch.setattr(
        service,
        "update_cash_balance",
        lambda user_id, total, currency="CNY": saved.update(
            user_id=user_id, total=total, currency=currency
        ),
    )

    result = service.confirm_account_balances(
        "balance-test",
        AccountBalancesUpdate(bank=1800, alipay=20.5, wechat=80, cash=100),
    )

    assert result.total == 2000.5
    assert [item.account_type for item in result.items] == ["bank", "alipay", "wechat", "cash"]
    assert saved == {"user_id": "balance-test", "total": 2000.5, "currency": "CNY"}


def test_missing_balance_snapshot_is_explicit(monkeypatch):
    monkeypatch.setattr(service, "get_account_balances_db", lambda user_id: [])

    result = service.get_account_balances("new-balance-user")

    assert result.items == []
    assert result.total == 0
    assert result.confirmed_at is None
