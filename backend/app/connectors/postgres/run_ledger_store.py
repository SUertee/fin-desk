"""PostgreSQL-backed storage adapter for agent harness run records."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models.runtime import AgentRunRecord
from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


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
                        output_tokens, total_tokens, cost_currency,
                        estimated_total_cost, record
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
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
                        cost_currency = EXCLUDED.cost_currency,
                        estimated_total_cost = EXCLUDED.estimated_total_cost,
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
                        run_record.cost.currency,
                        run_record.cost.estimated_total_cost,
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
            return row[0] if row else None
        except Exception:
            logger.exception("Failed to get agent run record request_id=%s", request_id)
            return None


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
                           output_tokens, total_tokens, cost_currency,
                           estimated_total_cost, created_at
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
                    "cost": {
                        "currency": row[14],
                        "estimated_total_cost": row[15],
                    },
                    "created_at": row[16].isoformat(),
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list agent run records for user=%s", user_id)
            return []
