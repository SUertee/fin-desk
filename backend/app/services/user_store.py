"""
User profile management with PostgreSQL persistence and in-memory cache.
"""

import logging

from app.connectors.postgres.profile_store import get_profile_db, save_profile_db
from app.models.user import ProfileUpdateRequest, UserProfile

logger = logging.getLogger(__name__)

_cache: dict[str, UserProfile] = {}


def get_profile(user_id: str) -> UserProfile:
    if user_id in _cache:
        return _cache[user_id]
    profile = get_profile_db(user_id)
    if profile:
        _cache[user_id] = profile
        return profile
    profile = UserProfile(user_id=user_id)
    _cache[user_id] = profile
    return profile


def update_profile(user_id: str, req: ProfileUpdateRequest) -> UserProfile:
    p = get_profile(user_id)
    if req.name is not None: p.name = req.name
    if req.occupation is not None: p.occupation = req.occupation
    if req.financial_goals is not None: p.financial_goals = req.financial_goals
    if req.risk_tolerance is not None: p.risk_tolerance = req.risk_tolerance
    if req.notes is not None: p.notes = req.notes
    if req.monthly_income is not None: p.monthly_income = req.monthly_income
    if req.monthly_expenses is not None: p.monthly_expenses = req.monthly_expenses
    if req.cash_balance is not None: p.assets.cash_balance = req.cash_balance
    if req.savings is not None: p.assets.savings = req.savings
    if req.investments is not None: p.assets.investments = req.investments
    if req.liabilities is not None: p.assets.liabilities = req.liabilities
    if req.preferences is not None: p.preferences = req.preferences
    _cache[user_id] = p
    save_profile_db(p)
    return p
