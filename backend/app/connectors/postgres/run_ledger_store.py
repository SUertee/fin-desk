"""PostgreSQL-backed storage adapter for agent harness run records."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.costing import AgentRunCost, MoneyAmount
from app.models.runtime import AgentRunRecord
from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


def normalize_agent_run_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical v2 contract, normalizing historical v1 JSON once."""

    if record.get("schema_version") == "agent-run-record/v2":
        return AgentRunRecord.model_validate(record).model_dump(mode="json")

    legacy = dict(record)
    legacy_cost = legacy.get("cost") if isinstance(legacy.get("cost"), dict) else {}
    currency = str(legacy_cost.get("currency") or "USD").upper()
    raw_total = legacy_cost.get("estimated_total_cost", 0)
    try:
        amount = Decimal(str(raw_total))
        if amount < 0:
            amount = None
    except (InvalidOperation, TypeError, ValueError):
        amount = None
    historical_total = (
        MoneyAmount(amount=amount, currency=currency) if amount is not None else None
    )
    legacy["schema_version"] = "agent-run-record/v2"
    legacy["cost"] = AgentRunCost(
        status="partial",
        issues=["historical_v1_detail_unavailable"],
        reporting_currency=currency,
        billing_totals=[historical_total] if historical_total is not None else [],
        reporting_total=historical_total,
        stages=[],
    ).model_dump(mode="json")
    return AgentRunRecord.model_validate(legacy).model_dump(mode="json")


def save_agent_run_record_db(record: AgentRunRecord | dict[str, Any]) -> bool:
    run_record = AgentRunRecord.model_validate(record)
    payload = run_record.model_dump(mode="json")

    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_run_records (
                        request_id, user_id, entrypoint, runtime_requested, runtime_used,
                        model_name, output_contract, audit_status, error_type,
                        request_count, model_response_count, input_tokens,
                        output_tokens, total_tokens, cost_status,
                        billing_totals, reporting_currency,
                        reporting_total_cost, record
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                    ON CONFLICT (request_id) DO UPDATE SET
                        runtime_used = EXCLUDED.runtime_used,
                        model_name = EXCLUDED.model_name,
                        output_contract = EXCLUDED.output_contract,
                        audit_status = EXCLUDED.audit_status,
                        error_type = EXCLUDED.error_type,
                        request_count = EXCLUDED.request_count,
                        model_response_count = EXCLUDED.model_response_count,
                        input_tokens = EXCLUDED.input_tokens,
                        output_tokens = EXCLUDED.output_tokens,
                        total_tokens = EXCLUDED.total_tokens,
                        cost_status = EXCLUDED.cost_status,
                        billing_totals = EXCLUDED.billing_totals,
                        reporting_currency = EXCLUDED.reporting_currency,
                        reporting_total_cost = EXCLUDED.reporting_total_cost,
                        record = EXCLUDED.record
                    """,
                    (
                        run_record.request_id,
                        run_record.user_id,
                        run_record.entrypoint,
                        run_record.runtime_requested,
                        run_record.runtime_used,
                        run_record.model_name,
                        run_record.output_contract,
                        run_record.audit_status,
                        run_record.error_type,
                        run_record.usage.request_count,
                        run_record.usage.model_response_count,
                        run_record.usage.input_tokens,
                        run_record.usage.output_tokens,
                        run_record.usage.total_tokens,
                        run_record.cost.status,
                        json.dumps(
                            [item.model_dump(mode="json") for item in run_record.cost.billing_totals],
                            ensure_ascii=False,
                        ),
                        run_record.cost.reporting_currency,
                        (
                            run_record.cost.reporting_total.amount
                            if run_record.cost.reporting_total is not None
                            else None
                        ),
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception(
                "Failed to save agent run record request_id=%s",
                run_record.request_id,
            )
            return False


def get_agent_run_record_db(request_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT record
                    FROM agent_run_records
                    WHERE request_id = %s
                    """,
                    (request_id,),
                )
                row = cur.fetchone()
            return normalize_agent_run_record(row[0]) if row else None
        except Exception:
            logger.exception("Failed to get agent run record request_id=%s", request_id)
            return None


def list_agent_run_cost_records_db(
    *,
    user_id: str,
    date_from: date,
    date_to: date,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Return bounded canonical run records for finance cost analytics."""

    safe_limit = max(1, min(limit, 5000))
    with get_conn() as conn:
        if not conn:
            raise RuntimeError("Agent run persistence is unavailable")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT record, created_at
                    FROM agent_run_records
                    WHERE user_id = %s
                      AND created_at >= %s
                      AND created_at < %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, date_from, date_to + timedelta(days=1), safe_limit),
                )
                rows = cur.fetchall()
            return [
                {
                    "record": normalize_agent_run_record(row[0]),
                    "created_at": row[1],
                }
                for row in rows
            ]
        except Exception as exc:
            logger.exception("Failed to read AI cost runs for user=%s", user_id)
            raise RuntimeError("Failed to read AI cost records") from exc


def list_agent_run_records_db(
    user_id: str,
    limit: int = 20,
    *,
    offset: int = 0,
    entrypoint: str | None = None,
    runtime_used: str | None = None,
    audit_status: str | None = None,
    has_error: bool | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if not conn:
            return []
        try:
            where_clauses = ["user_id = %s"]
            params: list[Any] = [user_id]
            if entrypoint:
                where_clauses.append("entrypoint = %s")
                params.append(entrypoint)
            if runtime_used:
                where_clauses.append("runtime_used = %s")
                params.append(runtime_used)
            if audit_status:
                where_clauses.append("audit_status = %s")
                params.append(audit_status)
            if has_error is True:
                where_clauses.append("error_type IS NOT NULL")
            elif has_error is False:
                where_clauses.append("error_type IS NULL")
            if created_from:
                where_clauses.append("created_at >= %s")
                params.append(created_from)
            if created_to:
                where_clauses.append("created_at <= %s")
                params.append(created_to)
            params.append(limit)
            params.append(offset)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT request_id, user_id, entrypoint, runtime_requested, runtime_used,
                           model_name, output_contract, audit_status, error_type,
                           request_count, model_response_count, input_tokens,
                           output_tokens, total_tokens, cost_status,
                           billing_totals, reporting_currency,
                           reporting_total_cost, created_at
                    FROM agent_run_records
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY created_at DESC
                    LIMIT %s
                    OFFSET %s
                    """,
                    params,
                )
                rows = cur.fetchall()
            return [
                {
                    "request_id": row[0],
                    "user_id": row[1],
                    "entrypoint": row[2],
                    "runtime_requested": row[3],
                    "runtime_used": row[4],
                    "model_name": row[5],
                    "output_contract": row[6],
                    "audit_status": row[7],
                    "error_type": row[8],
                    "usage": {
                        "request_count": row[9],
                        "model_response_count": row[10],
                        "input_tokens": row[11],
                        "output_tokens": row[12],
                        "total_tokens": row[13],
                    },
                    "cost": AgentRunCost(
                        status=row[14],
                        billing_totals=row[15] or [],
                        reporting_currency=row[16],
                        reporting_total=(
                            MoneyAmount(amount=row[17], currency=row[16])
                            if row[17] is not None
                            else None
                        ),
                    ).model_dump(mode="json"),
                    "created_at": row[18].isoformat(),
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list agent run records for user=%s", user_id)
            return []
