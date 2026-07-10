"""PostgreSQL-backed storage adapter for transactions and analysis snapshots."""

import json
import logging
from typing import Any, Optional

from app.connectors.postgres.connection import get_conn

logger = logging.getLogger(__name__)


def list_transactions_db(
    user_id: str,
    limit: int = 200,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    with get_conn() as conn:
        if not conn:
            return []
        try:
            conditions = ["user_id = %s"]
            params: list = [user_id]
            if date_from:
                conditions.append("date >= %s")
                params.append(date_from)
            if date_to:
                conditions.append("date <= %s")
                params.append(date_to)
            params.append(limit)
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, user_id, date, month, description, counterparty, amount,
                           gross_amount, currency, balance, direction, type, category, status,
                           payment_method, external_id, merchant_order_id, source,
                           source_file, source_format, note, is_duplicate, raw, created_at,
                           duplicate_reason, duplicate_of
                    FROM transactions
                    WHERE {' AND '.join(conditions)}
                    ORDER BY date ASC, id ASC
                    LIMIT %s
                    """,
                    params,
                )
                rows = cur.fetchall()
            results = []
            for row in rows:
                results.append(
                    {
                        "id": str(row[0]),
                        "user_id": row[1],
                        "date": row[2].isoformat(),
                        "month": row[3],
                        "description": row[4],
                        "counterparty": row[5],
                        "amount": float(row[6]),
                        "gross_amount": float(row[7]),
                        "currency": row[8],
                        "balance": float(row[9]) if row[9] is not None else None,
                        "direction": row[10],
                        "type": row[11],
                        "category": row[12],
                        "status": row[13],
                        "payment_method": row[14],
                        "external_id": row[15],
                        "merchant_order_id": row[16],
                        "source": row[17],
                        "source_file": row[18],
                        "source_format": row[19],
                        "note": row[20],
                        "is_duplicate": row[21],
                        "raw": row[22],
                        "created_at": row[23].isoformat(),
                        "duplicate_reason": row[24],
                        "duplicate_of": row[25],
                    }
                )
            return results
        except Exception:
            logger.exception("Failed to list transactions for user=%s", user_id)
            return []


def count_transactions_db(user_id: str) -> int:
    with get_conn() as conn:
        if not conn:
            return 0
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM transactions WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
            return int(row[0]) if row else 0
        except Exception:
            logger.exception("Failed to count transactions for user=%s", user_id)
            return 0


def insert_transactions_db(user_id: str, transactions: list[dict[str, Any]]) -> bool:
    """Append imported transactions; existing rows are never deleted."""

    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    for tx in transactions:
                        cur.execute(
                            """
                            INSERT INTO transactions (
                                user_id, date, month, description, counterparty, amount,
                                gross_amount, currency, balance, direction, type, category, status,
                                payment_method, external_id, merchant_order_id, source,
                                source_file, source_format, note, is_duplicate,
                                duplicate_reason, duplicate_of, raw
                            )
                            VALUES (
                                %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s::jsonb
                            )
                            """,
                            (
                                user_id,
                                tx["date"],
                                tx["month"],
                                tx.get("description", ""),
                                tx.get("counterparty", ""),
                                tx.get("amount", 0),
                                tx.get("gross_amount", abs(tx.get("amount", 0))),
                                tx.get("currency", "CNY"),
                                tx.get("balance"),
                                tx.get("direction", ""),
                                tx.get("type", ""),
                                tx.get("category", "other"),
                                tx.get("status", ""),
                                tx.get("payment_method", ""),
                                tx.get("external_id", ""),
                                tx.get("merchant_order_id", ""),
                                tx.get("source", "manual"),
                                tx.get("source_file", ""),
                                tx.get("source_format", ""),
                                tx.get("note", ""),
                                tx.get("is_duplicate", False),
                                tx.get("duplicate_reason", ""),
                                tx.get("duplicate_of", ""),
                                json.dumps(tx.get("raw", {}), ensure_ascii=False),
                            ),
                        )
            return True
        except Exception:
            logger.exception("Failed to insert transactions for user=%s", user_id)
            return False


def list_external_ids_db(user_id: str) -> set[str]:
    """Existing non-empty external ids for idempotent re-import checks."""

    with get_conn() as conn:
        if not conn:
            return set()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT external_id FROM transactions WHERE user_id = %s AND external_id <> ''",
                    (user_id,),
                )
                return {row[0] for row in cur.fetchall()}
        except Exception:
            logger.exception("Failed to list external ids for user=%s", user_id)
            return set()


def list_transactions_window_db(
    user_id: str, date_from: str, date_to: str
) -> list[dict[str, Any]]:
    """Stored transactions inside a date window, for cross-source dedup."""

    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, date, amount, counterparty, description, source,
                           is_duplicate, payment_method, external_id
                    FROM transactions
                    WHERE user_id = %s AND date BETWEEN %s AND %s
                    ORDER BY date ASC, id ASC
                    """,
                    (user_id, date_from, date_to),
                )
                rows = cur.fetchall()
            return [
                {
                    "id": str(row[0]),
                    "date": row[1].isoformat(),
                    "amount": float(row[2]),
                    "counterparty": row[3],
                    "description": row[4],
                    "source": row[5],
                    "is_duplicate": row[6],
                    "payment_method": row[7],
                    "external_id": row[8],
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list transaction window for user=%s", user_id)
            return []


AGGREGATE_GROUP_COLUMNS = {
    "category": "category",
    "month": "month",
    "counterparty": "counterparty",
    "day": "date",
}


def aggregate_transactions_db(
    user_id: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
    merchant_contains: str | None = None,
    direction: str | None = None,  # "expense" | "income"
    group_by: str | None = None,  # category | month | counterparty | day
) -> dict[str, Any]:
    """Parameterized aggregation over the active ledger (duplicates excluded).

    Filters are typed parameters bound into SQL — callers can never inject
    SQL text. Returns totals plus optional grouped rows.
    """

    with get_conn() as conn:
        if not conn:
            return {"total": 0.0, "count": 0, "groups": []}
        conditions = ["user_id = %s", "NOT is_duplicate"]
        params: list[Any] = [user_id]
        if date_from:
            conditions.append("date >= %s")
            params.append(date_from)
        if date_to:
            conditions.append("date <= %s")
            params.append(date_to)
        if category:
            conditions.append("category = %s")
            params.append(category)
        if merchant_contains:
            conditions.append("(counterparty ILIKE %s OR description ILIKE %s)")
            params.extend([f"%{merchant_contains}%", f"%{merchant_contains}%"])
        if direction == "expense":
            conditions.append("amount < 0")
        elif direction == "income":
            conditions.append("amount > 0")
        where = " AND ".join(conditions)
        # abs() so expense totals read as positive spend figures
        amount_expr = "SUM(ABS(amount))" if direction else "SUM(amount)"
        group_column = AGGREGATE_GROUP_COLUMNS.get(group_by or "")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COALESCE({amount_expr}, 0), COUNT(*) FROM transactions WHERE {where}",
                    params,
                )
                total_row = cur.fetchone()
                groups: list[dict[str, Any]] = []
                if group_column:
                    cur.execute(
                        f"""
                        SELECT {group_column}, COALESCE({amount_expr}, 0), COUNT(*)
                        FROM transactions WHERE {where}
                        GROUP BY {group_column}
                        ORDER BY 2 DESC
                        LIMIT 20
                        """,
                        params,
                    )
                    groups = [
                        {
                            "key": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
                            "total": round(float(row[1]), 2),
                            "count": int(row[2]),
                        }
                        for row in cur.fetchall()
                    ]
            return {
                "total": round(float(total_row[0]), 2) if total_row else 0.0,
                "count": int(total_row[1]) if total_row else 0,
                "groups": groups,
            }
        except Exception:
            logger.exception("Failed to aggregate transactions for user=%s", user_id)
            return {"total": 0.0, "count": 0, "groups": []}


def list_daily_totals_db(
    user_id: str, date_from: str, date_to: str
) -> list[dict[str, Any]]:
    """Per-day expense/income aggregates, excluding flagged duplicates."""

    with get_conn() as conn:
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT date,
                           COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0),
                           COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0),
                           COUNT(*)
                    FROM transactions
                    WHERE user_id = %s AND date BETWEEN %s AND %s
                          AND NOT is_duplicate
                    GROUP BY date
                    ORDER BY date ASC
                    """,
                    (user_id, date_from, date_to),
                )
                rows = cur.fetchall()
            return [
                {
                    "date": row[0].isoformat(),
                    "expense": round(float(row[1]), 2),
                    "income": round(float(row[2]), 2),
                    "count": int(row[3]),
                }
                for row in rows
            ]
        except Exception:
            logger.exception("Failed to list daily totals for user=%s", user_id)
            return []


def get_latest_analysis_run_db(user_id: str) -> Optional[dict]:
    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, created_at, period_start, period_end,
                           monthly_totals, input, output, source
                    FROM analysis_runs
                    WHERE user_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            if not row:
                return None
            return {
                "id": str(row[0]),
                "user_id": row[1],
                "created_at": row[2].isoformat(),
                "period_start": row[3].isoformat() if row[3] else None,
                "period_end": row[4].isoformat() if row[4] else None,
                "monthly_totals": row[5],
                "input": row[6],
                "output": row[7],
                "source": row[8],
            }
        except Exception:
            logger.exception("Failed to get latest analysis run for user=%s", user_id)
            return None


def replace_latest_analysis_run_db(
    user_id: str,
    period_start: Optional[str],
    period_end: Optional[str],
    monthly_totals: list[dict[str, Any]],
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    source: str = "statement_import",
) -> bool:
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM analysis_runs WHERE user_id = %s", (user_id,))
                    cur.execute(
                        """
                        INSERT INTO analysis_runs (
                            user_id, period_start, period_end, monthly_totals, input, output, source
                        )
                        VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                        """,
                        (
                            user_id,
                            period_start,
                            period_end,
                            json.dumps(monthly_totals, ensure_ascii=False),
                            json.dumps(input_payload, ensure_ascii=False),
                            json.dumps(output_payload, ensure_ascii=False),
                            source,
                        ),
                    )
            return True
        except Exception:
            logger.exception("Failed to replace analysis run for user=%s", user_id)
            return False
