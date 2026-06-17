"""
Analysis-related Pydantic models: request and response for /analyze.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    user_id: str
    transactions: List[Dict[str, Any]]
    monthly_totals: List[Dict[str, Any]]


class AnalyzeResponse(BaseModel):
    ok: bool
    meta: Dict[str, Any]
    monthly_totals: List[Dict[str, Any]]
    category_summary: Dict[str, Any]
    anomalies: List[Dict[str, Any]]
    insights: List[str]
    actions: List[str]
    budget: Dict[str, Any]
    notes: str = ""
    debug: Optional[Dict[str, Any]] = None
