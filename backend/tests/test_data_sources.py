from app.routes import data_sources as data_sources_route
from app.services import data_sources


def test_data_source_status_includes_latest_import(monkeypatch):
    monkeypatch.setattr(data_sources, "count_transactions_db", lambda user_id: 42)
    monkeypatch.setattr(
        data_sources,
        "get_latest_statement_import_record_db",
        lambda user_id: {
            "import_id": "imp_1",
            "user_id": user_id,
            "source_file": "statement.csv",
            "source_format": "csv",
            "imported_count": 42,
            "status": "succeeded",
            "error": "",
            "sample": [],
            "created_at": "2026-06-30T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        data_sources,
        "list_statement_import_records_db",
        lambda user_id, limit=5: [data_sources.get_latest_statement_import_record_db(user_id)],
    )

    result = data_sources_route.get_user_data_source_status("demo")

    assert result["ok"] is True
    assert result["transaction_count"] == 42
    assert result["latest_import"]["source_file"] == "statement.csv"
    assert {channel["id"] for channel in result["channels"]} >= {
        "alipay_csv",
        "wechat_csv",
        "bank_csv",
    }
