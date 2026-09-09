"""PostgreSQL storage for user-confirmed account balance snapshots."""

import logging
from datetime import datetime

from app.connectors.postgres.connection import get_conn
from app.models.account_balances import AccountBalanceItem

logger = logging.getLogger(__name__)


def get_account_balances_db(user_id: str) -> list[AccountBalanceItem]:
    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT account_type, amount, currency, confirmed_at
                    FROM account_balances
                    WHERE user_id = %s
                    ORDER BY CASE account_type
                        WHEN 'bank' THEN 1 WHEN 'alipay' THEN 2
                        WHEN 'wechat' THEN 3 ELSE 4 END
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
            return [
                AccountBalanceItem(
                    account_type=row[0], amount=float(row[1]),
                    currency=row[2], confirmed_at=row[3],
                )
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to load account balances for user=%s", user_id)
            return []


def save_account_balances_db(
    user_id: str, items: list[AccountBalanceItem], confirmed_at: datetime
) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                for item in items:
                    cur.execute(
                        """
                        INSERT INTO account_balances (
                            user_id, account_type, amount, currency,
                            confirmed_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, account_type) DO UPDATE SET
                            amount = EXCLUDED.amount,
                            currency = EXCLUDED.currency,
                            confirmed_at = EXCLUDED.confirmed_at,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (
                            user_id, item.account_type, item.amount,
                            item.currency, confirmed_at, confirmed_at,
                        ),
                    )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save account balances for user=%s", user_id)
            return False
