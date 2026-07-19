"""PostgreSQL persistence for investment state and immutable market quotes."""

from __future__ import annotations

import logging
from datetime import datetime

from app.connectors.postgres.connection import get_conn
from app.models.costing import MoneyAmount
from app.models.investments import (
    InvestmentAccount,
    InvestmentPosition,
    MarketInstrument,
    MarketQuote,
)


logger = logging.getLogger(__name__)


def save_investment_account_db(account: InvestmentAccount | dict) -> bool:
    parsed = InvestmentAccount.model_validate(account)
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO investment_accounts (
                        user_id, account_id, name, account_type, provider,
                        base_currency, status, as_of
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, account_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        account_type = EXCLUDED.account_type,
                        provider = EXCLUDED.provider,
                        base_currency = EXCLUDED.base_currency,
                        status = EXCLUDED.status,
                        as_of = EXCLUDED.as_of,
                        updated_at = NOW()
                    """,
                    (
                        parsed.user_id,
                        parsed.account_id,
                        parsed.name,
                        parsed.account_type,
                        parsed.provider,
                        parsed.base_currency,
                        parsed.status,
                        parsed.as_of,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save investment account=%s", parsed.account_id)
            return False


def replace_investment_positions_db(
    user_id: str,
    account_id: str,
    positions: list[InvestmentPosition | dict],
) -> bool:
    parsed = [InvestmentPosition.model_validate(position) for position in positions]
    if any(
        position.user_id != user_id or position.account_id != account_id
        for position in parsed
    ):
        raise ValueError("all positions must belong to the requested user and account")

    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM investment_positions WHERE user_id = %s AND account_id = %s",
                        (user_id, account_id),
                    )
                    for position in parsed:
                        average_amount = (
                            position.average_cost.amount if position.average_cost else None
                        )
                        average_currency = (
                            position.average_cost.currency if position.average_cost else None
                        )
                        cur.execute(
                            """
                            INSERT INTO investment_positions (
                                user_id, account_id, symbol, asset_type, quantity,
                                average_cost_amount, average_cost_currency, as_of
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                position.user_id,
                                position.account_id,
                                position.symbol,
                                position.asset_type,
                                position.quantity,
                                average_amount,
                                average_currency,
                                position.as_of,
                            ),
                        )
            return True
        except Exception:
            logger.exception("Failed to replace investment positions account=%s", account_id)
            return False


def list_investment_accounts_db(user_id: str, limit: int = 50) -> list[InvestmentAccount]:
    bounded = min(max(limit, 1), 50)
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, account_id, name, account_type, provider,
                           base_currency, status, as_of
                    FROM investment_accounts
                    WHERE user_id = %s
                    ORDER BY updated_at DESC, account_id ASC
                    LIMIT %s
                    """,
                    (user_id, bounded),
                )
                rows = cur.fetchall()
            return [
                InvestmentAccount(
                    user_id=row[0],
                    account_id=row[1],
                    name=row[2],
                    account_type=row[3],
                    provider=row[4],
                    base_currency=row[5],
                    status=row[6],
                    as_of=row[7],
                )
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list investment accounts user=%s", user_id)
            return []


def list_investment_positions_db(
    user_id: str,
    limit: int = 500,
) -> list[InvestmentPosition]:
    bounded = min(max(limit, 1), 500)
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, account_id, symbol, asset_type, quantity,
                           average_cost_amount, average_cost_currency, as_of
                    FROM investment_positions
                    WHERE user_id = %s
                    ORDER BY account_id ASC, symbol ASC
                    LIMIT %s
                    """,
                    (user_id, bounded),
                )
                rows = cur.fetchall()
            return [
                InvestmentPosition(
                    user_id=row[0],
                    account_id=row[1],
                    symbol=row[2],
                    asset_type=row[3],
                    quantity=row[4],
                    average_cost=(
                        MoneyAmount(amount=row[5], currency=row[6])
                        if row[5] is not None and row[6]
                        else None
                    ),
                    as_of=row[7],
                )
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list investment positions user=%s", user_id)
            return []


def save_market_quote_snapshot_db(quote: MarketQuote | dict) -> bool:
    parsed = MarketQuote.model_validate(quote)
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO market_quote_snapshots (
                        symbol, asset_type, price, currency, quote_as_of,
                        quote_source, venue
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                        symbol, asset_type, quote_as_of, quote_source, venue
                    ) DO NOTHING
                    """,
                    (
                        parsed.symbol,
                        parsed.asset_type,
                        parsed.price.amount,
                        parsed.price.currency,
                        parsed.quote_as_of,
                        parsed.source,
                        parsed.venue,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save market quote symbol=%s", parsed.symbol)
            return False


def list_latest_market_quotes_db(
    instruments: list[MarketInstrument],
    *,
    as_of: datetime,
    limit: int = 200,
) -> list[MarketQuote]:
    bounded = list(dict.fromkeys(instruments))[: min(max(limit, 1), 200)]
    if not bounded:
        return []
    values = ", ".join(["(%s, %s)"] * len(bounded))
    params: list[object] = []
    for item in bounded:
        params.extend([item.symbol, item.asset_type])
    params.append(as_of)

    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH requested(symbol, asset_type) AS (VALUES {values})
                    SELECT DISTINCT ON (q.symbol, q.asset_type)
                           q.symbol, q.asset_type, q.price, q.currency,
                           q.quote_as_of, q.quote_source, q.venue
                    FROM market_quote_snapshots q
                    JOIN requested r
                      ON r.symbol = q.symbol AND r.asset_type = q.asset_type
                    WHERE q.quote_as_of <= %s
                    ORDER BY q.symbol, q.asset_type, q.quote_as_of DESC, q.fetched_at DESC
                    """,
                    params,
                )
                rows = cur.fetchall()
            return [
                MarketQuote(
                    symbol=row[0],
                    asset_type=row[1],
                    price=MoneyAmount(amount=row[2], currency=row[3]),
                    quote_as_of=row[4],
                    source=row[5],
                    venue=row[6],
                )
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list latest market quotes")
            return []
