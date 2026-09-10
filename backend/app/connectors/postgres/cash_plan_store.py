"""PostgreSQL storage for a user's forward-looking cash plan."""

import json
import logging
from datetime import datetime, timezone

from app.connectors.postgres.connection import get_conn
from app.models.cash_plan import CashPlan

logger = logging.getLogger(__name__)


class CashPlanStorageError(RuntimeError):
    """Raised when cash-plan persistence is unavailable or fails."""


def get_cash_plan_db(user_id: str) -> CashPlan | None:
    with get_conn() as conn:
        if not conn:
            raise CashPlanStorageError("Cash-plan storage is unavailable")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, currency, cash_balance, daily_budget,
                           monthly_budget, entries, updated_at
                    FROM cash_plans WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            if not row:
                return None
            entries = row[5]
            if isinstance(entries, str):
                entries = json.loads(entries)
            return CashPlan(
                user_id=row[0], currency=row[1], cash_balance=float(row[2]),
                daily_budget=float(row[3]), monthly_budget=float(row[4]),
                entries=entries or [], updated_at=row[6],
            )
        except Exception as exc:
            logger.exception("Failed to load cash plan for user=%s", user_id)
            raise CashPlanStorageError("Failed to load cash plan") from exc


def save_cash_plan_db(plan: CashPlan) -> bool:
    plan.updated_at = datetime.now(timezone.utc)
    with get_conn() as conn:
        if not conn:
            raise CashPlanStorageError("Cash-plan storage is unavailable")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cash_plans (
                        user_id, currency, cash_balance, daily_budget,
                        monthly_budget, entries, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        currency = EXCLUDED.currency,
                        cash_balance = EXCLUDED.cash_balance,
                        daily_budget = EXCLUDED.daily_budget,
                        monthly_budget = EXCLUDED.monthly_budget,
                        entries = EXCLUDED.entries,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        plan.user_id, plan.currency, plan.cash_balance,
                        plan.daily_budget, plan.monthly_budget,
                        json.dumps([entry.model_dump(mode="json") for entry in plan.entries]),
                        plan.updated_at,
                    ),
                )
            conn.commit()
            return True
        except Exception as exc:
            logger.exception("Failed to save cash plan for user=%s", plan.user_id)
            raise CashPlanStorageError("Failed to save cash plan") from exc
