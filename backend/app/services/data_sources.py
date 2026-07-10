"""Application service for user data-source status."""

from __future__ import annotations

from typing import Any

from app.connectors.postgres.statement_import_store import (
    get_latest_statement_import_record_db,
    list_statement_import_records_db,
)
from app.connectors.postgres.transactions_store import count_transactions_db


def get_data_source_status(user_id: str) -> dict[str, Any]:
    latest_import = get_latest_statement_import_record_db(user_id)
    import_history = list_statement_import_records_db(user_id, limit=5)
    transaction_count = count_transactions_db(user_id)

    return {
        "ok": True,
        "user_id": user_id,
        "transaction_count": transaction_count,
        "latest_import": latest_import,
        "import_history": import_history,
        "channels": [
            {
                "id": "alipay_csv",
                "label": "Alipay statement",
                "status": "ready",
                "mode": "csv_upload",
                "recommended": True,
            },
            {
                "id": "wechat_csv",
                "label": "WeChat statement",
                "status": "planned",
                "mode": "csv_upload",
                "recommended": False,
            },
            {
                "id": "bank_csv",
                "label": "Bank CSV / PDF upload",
                "status": "csv_enabled",
                "mode": "csv_upload",
                "recommended": False,
            },
        ],
    }
