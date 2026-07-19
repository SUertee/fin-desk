"""PostgreSQL-backed storage adapter for user profiles."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.config.settings import get_settings
from app.connectors.postgres.connection import get_conn
from app.models.user import (
    AssetSnapshot,
    CostReportingPreferences,
    UserPreferences,
    UserProfile,
)

logger = logging.getLogger(__name__)


def get_profile_db(user_id: str) -> Optional[UserProfile]:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, name, occupation, financial_goals, risk_tolerance,
                           cash_balance, savings, investments, liabilities,
                           monthly_income, monthly_expenses, notes, preferences,
                           cost_preferences
                    FROM user_profiles
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            if not row:
                return None

            goals = row[3]
            if isinstance(goals, str):
                goals = json.loads(goals)
            raw_preferences = row[12]
            if isinstance(raw_preferences, str):
                raw_preferences = json.loads(raw_preferences)
            raw_cost_preferences = row[13]
            if isinstance(raw_cost_preferences, str):
                raw_cost_preferences = json.loads(raw_cost_preferences)
            if not raw_cost_preferences:
                raw_cost_preferences = {
                    "reporting_currency": get_settings().cost.reporting_currency
                }

            return UserProfile(
                user_id=row[0],
                name=row[1] or "",
                occupation=row[2] or "",
                financial_goals=goals or [],
                risk_tolerance=row[4] or "moderate",
                assets=AssetSnapshot(
                    cash_balance=float(row[5] or 0),
                    savings=float(row[6] or 0),
                    investments=float(row[7] or 0),
                    liabilities=float(row[8] or 0),
                ),
                monthly_income=float(row[9] or 0),
                monthly_expenses=float(row[10] or 0),
                notes=row[11] or "",
                preferences=UserPreferences.model_validate(raw_preferences or {}),
                cost_preferences=CostReportingPreferences.model_validate(
                    raw_cost_preferences
                ),
            )
        except Exception:
            logger.exception("Failed to get profile for user=%s", user_id)
            return None


def save_profile_db(profile: UserProfile) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_profiles (
                        user_id, name, occupation, financial_goals, risk_tolerance,
                        cash_balance, savings, investments, liabilities,
                        monthly_income, monthly_expenses, notes, preferences,
                        cost_preferences, updated_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        occupation = EXCLUDED.occupation,
                        financial_goals = EXCLUDED.financial_goals,
                        risk_tolerance = EXCLUDED.risk_tolerance,
                        cash_balance = EXCLUDED.cash_balance,
                        savings = EXCLUDED.savings,
                        investments = EXCLUDED.investments,
                        liabilities = EXCLUDED.liabilities,
                        monthly_income = EXCLUDED.monthly_income,
                        monthly_expenses = EXCLUDED.monthly_expenses,
                        notes = EXCLUDED.notes,
                        preferences = EXCLUDED.preferences,
                        cost_preferences = EXCLUDED.cost_preferences,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        profile.user_id,
                        profile.name,
                        profile.occupation,
                        json.dumps(profile.financial_goals),
                        profile.risk_tolerance,
                        profile.assets.cash_balance,
                        profile.assets.savings,
                        profile.assets.investments,
                        profile.assets.liabilities,
                        profile.monthly_income,
                        profile.monthly_expenses,
                        profile.notes,
                        json.dumps(profile.preferences.model_dump()),
                        json.dumps(profile.cost_preferences.model_dump(mode="json")),
                        datetime.now(timezone.utc),
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception("Failed to save profile for user=%s", profile.user_id)
            return False
