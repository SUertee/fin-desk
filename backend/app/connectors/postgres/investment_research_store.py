"""PostgreSQL persistence for research watchlists and hypothetical scenarios."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.connectors.postgres.connection import get_conn
from app.models.costing import MoneyAmount
from app.models.investment_research import (
    InvestmentScenario,
    InvestmentScenarioDetail,
    ScenarioPosition,
    ScenarioPositionRequest,
    WatchlistItem,
)
from app.models.market_data import MarketAssetType


logger = logging.getLogger(__name__)


def list_watchlist_items_db(user_id: str, limit: int = 100) -> list[WatchlistItem]:
    bounded = min(max(limit, 1), 100)
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, symbol, asset_type, note, created_at, updated_at
                    FROM investment_watchlist_items
                    WHERE user_id = %s
                    ORDER BY updated_at DESC, symbol ASC
                    LIMIT %s
                    """,
                    (user_id, bounded),
                )
                rows = cur.fetchall()
            return [
                WatchlistItem(
                    user_id=row[0],
                    symbol=row[1],
                    asset_type=row[2],
                    note=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list investment watchlist user=%s", user_id)
            return []


def save_watchlist_item_db(item: WatchlistItem | dict) -> bool:
    parsed = WatchlistItem.model_validate(item)
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO investment_watchlist_items (
                        user_id, symbol, asset_type, note, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, symbol, asset_type) DO UPDATE SET
                        note = EXCLUDED.note,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        parsed.user_id,
                        parsed.symbol,
                        parsed.asset_type,
                        parsed.note,
                        parsed.created_at,
                        parsed.updated_at,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception(
                "Failed to save watchlist item user=%s symbol=%s",
                parsed.user_id,
                parsed.symbol,
            )
            return False


def delete_watchlist_item_db(
    user_id: str,
    symbol: str,
    asset_type: MarketAssetType,
) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM investment_watchlist_items
                    WHERE user_id = %s AND symbol = %s AND asset_type = %s
                    """,
                    (user_id, symbol, asset_type),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception(
                "Failed to delete watchlist item user=%s symbol=%s",
                user_id,
                symbol,
            )
            return False


def list_investment_scenarios_db(
    user_id: str,
    limit: int = 50,
) -> list[InvestmentScenario]:
    bounded = min(max(limit, 1), 50)
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, scenario_id, name, reporting_currency,
                           starting_cash_amount, created_at, updated_at
                    FROM investment_scenarios
                    WHERE user_id = %s
                    ORDER BY updated_at DESC, scenario_id ASC
                    LIMIT %s
                    """,
                    (user_id, bounded),
                )
                rows = cur.fetchall()
            return [_scenario_from_row(row) for row in rows]
        except Exception:
            logger.exception("Failed to list investment scenarios user=%s", user_id)
            return []


def save_investment_scenario_db(scenario: InvestmentScenario | dict) -> bool:
    parsed = InvestmentScenario.model_validate(scenario)
    starting_cash = parsed.starting_cash.amount if parsed.starting_cash else None
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO investment_scenarios (
                        user_id, scenario_id, name, reporting_currency,
                        starting_cash_amount, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, scenario_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        reporting_currency = EXCLUDED.reporting_currency,
                        starting_cash_amount = EXCLUDED.starting_cash_amount,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        parsed.user_id,
                        parsed.scenario_id,
                        parsed.name,
                        parsed.reporting_currency,
                        starting_cash,
                        parsed.created_at,
                        parsed.updated_at,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception(
                "Failed to save investment scenario user=%s scenario=%s",
                parsed.user_id,
                parsed.scenario_id,
            )
            return False


def get_investment_scenario_db(
    user_id: str,
    scenario_id: str,
) -> InvestmentScenarioDetail | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, scenario_id, name, reporting_currency,
                           starting_cash_amount, created_at, updated_at
                    FROM investment_scenarios
                    WHERE user_id = %s AND scenario_id = %s
                    """,
                    (user_id, scenario_id),
                )
                scenario_row = cur.fetchone()
                if scenario_row is None:
                    return None
                cur.execute(
                    """
                    SELECT user_id, scenario_id, symbol, asset_type, quantity,
                           created_at, updated_at
                    FROM investment_scenario_positions
                    WHERE user_id = %s AND scenario_id = %s
                    ORDER BY symbol ASC
                    """,
                    (user_id, scenario_id),
                )
                position_rows = cur.fetchall()
            return InvestmentScenarioDetail(
                scenario=_scenario_from_row(scenario_row),
                positions=[
                    ScenarioPosition(
                        user_id=row[0],
                        scenario_id=row[1],
                        symbol=row[2],
                        asset_type=row[3],
                        quantity=row[4],
                        created_at=row[5],
                        updated_at=row[6],
                    )
                    for row in position_rows
                ],
            )
        except Exception:
            logger.exception(
                "Failed to load investment scenario user=%s scenario=%s",
                user_id,
                scenario_id,
            )
            return None


def replace_scenario_positions_db(
    user_id: str,
    scenario_id: str,
    positions: list[ScenarioPositionRequest | dict],
) -> bool:
    parsed = [ScenarioPositionRequest.model_validate(item) for item in positions]
    now = datetime.now(timezone.utc)
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM investment_scenarios
                        WHERE user_id = %s AND scenario_id = %s
                        """,
                        (user_id, scenario_id),
                    )
                    if cur.fetchone() is None:
                        return False
                    cur.execute(
                        """
                        DELETE FROM investment_scenario_positions
                        WHERE user_id = %s AND scenario_id = %s
                        """,
                        (user_id, scenario_id),
                    )
                    for item in parsed:
                        cur.execute(
                            """
                            INSERT INTO investment_scenario_positions (
                                user_id, scenario_id, symbol, asset_type, quantity,
                                created_at, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                user_id,
                                scenario_id,
                                item.symbol,
                                item.asset_type,
                                item.quantity,
                                now,
                                now,
                            ),
                        )
                    cur.execute(
                        """
                        UPDATE investment_scenarios SET updated_at = %s
                        WHERE user_id = %s AND scenario_id = %s
                        """,
                        (now, user_id, scenario_id),
                    )
            return True
        except Exception:
            logger.exception(
                "Failed to replace scenario positions user=%s scenario=%s",
                user_id,
                scenario_id,
            )
            return False


def delete_investment_scenario_db(user_id: str, scenario_id: str) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM investment_scenarios
                    WHERE user_id = %s AND scenario_id = %s
                    """,
                    (user_id, scenario_id),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception(
                "Failed to delete investment scenario user=%s scenario=%s",
                user_id,
                scenario_id,
            )
            return False


def _scenario_from_row(row) -> InvestmentScenario:
    starting_cash = (
        MoneyAmount(amount=row[4], currency=row[3]) if row[4] is not None else None
    )
    return InvestmentScenario(
        user_id=row[0],
        scenario_id=row[1],
        name=row[2],
        reporting_currency=row[3],
        starting_cash=starting_cash,
        created_at=row[5],
        updated_at=row[6],
    )
