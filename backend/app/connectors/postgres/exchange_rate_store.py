"""PostgreSQL persistence for immutable exchange-rate snapshots."""

from __future__ import annotations

import logging
from datetime import date

from app.connectors.postgres.connection import get_conn
from app.models.costing import ExchangeRateSnapshot, normalize_currency
from app.runtime.costing.service import identity_exchange_rate


logger = logging.getLogger(__name__)


def save_exchange_rate_snapshot_db(
    snapshot: ExchangeRateSnapshot | dict,
) -> bool:
    parsed = ExchangeRateSnapshot.model_validate(snapshot)
    if parsed.exchange_rate_source == "identity":
        return True
    with get_conn() as conn:
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO exchange_rate_snapshots (
                        billing_currency, reporting_currency, exchange_rate,
                        exchange_rate_date, exchange_rate_source
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (
                        billing_currency, reporting_currency,
                        exchange_rate_date, exchange_rate_source
                    ) DO NOTHING
                    """,
                    (
                        parsed.billing_currency,
                        parsed.reporting_currency,
                        parsed.exchange_rate,
                        parsed.exchange_rate_date,
                        parsed.exchange_rate_source,
                    ),
                )
            conn.commit()
            return True
        except Exception:
            logger.exception(
                "Failed to save exchange-rate snapshot %s/%s for %s",
                parsed.billing_currency,
                parsed.reporting_currency,
                parsed.exchange_rate_date,
            )
            return False


def get_exchange_rate_snapshot_db(
    billing_currency: str,
    reporting_currency: str,
    exchange_rate_date: date,
) -> ExchangeRateSnapshot | None:
    billing = normalize_currency(billing_currency)
    reporting = normalize_currency(reporting_currency)
    identity = identity_exchange_rate(billing, reporting, exchange_rate_date)
    if identity is not None:
        return identity

    with get_conn() as conn:
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT billing_currency, reporting_currency, exchange_rate,
                           exchange_rate_date, exchange_rate_source
                    FROM exchange_rate_snapshots
                    WHERE billing_currency = %s
                      AND reporting_currency = %s
                      AND exchange_rate_date <= %s
                    ORDER BY exchange_rate_date DESC, created_at DESC
                    LIMIT 1
                    """,
                    (billing, reporting, exchange_rate_date),
                )
                row = cur.fetchone()
            if row is None:
                return None
            return ExchangeRateSnapshot(
                billing_currency=row[0],
                reporting_currency=row[1],
                exchange_rate=row[2],
                exchange_rate_date=row[3],
                exchange_rate_source=row[4],
            )
        except Exception:
            logger.exception(
                "Failed to load exchange-rate snapshot %s/%s for %s",
                billing,
                reporting,
                exchange_rate_date,
            )
            return None
