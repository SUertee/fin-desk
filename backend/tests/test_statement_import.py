"""Statement import service and route tests."""

from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from app.routes import statement_import as statement_import_route
from app.services import statement_import_service
from tests.statement_fixtures import (
    GENERIC_CSV,
    alipay_csv_bytes,
    wechat_xlsx_bytes,
)


@pytest.fixture
def store(monkeypatch):
    """Fake persistence layer capturing inserts, with seedable state."""

    state = {
        "inserted": [],
        "external_ids": set(),
        "window": [],
        "records": [],
    }

    def fake_insert(user_id, transactions):
        state["inserted"].append((user_id, transactions))
        return True

    monkeypatch.setattr(statement_import_service, "insert_transactions_db", fake_insert)
    monkeypatch.setattr(
        statement_import_service,
        "list_external_ids_db",
        lambda user_id: set(state["external_ids"]),
    )
    monkeypatch.setattr(
        statement_import_service,
        "list_transactions_window_db",
        lambda user_id, date_from, date_to: list(state["window"]),
    )

    def fake_record(**kwargs):
        state["records"].append(kwargs)
        return {"import_id": "imp_test", **kwargs}

    monkeypatch.setattr(
        statement_import_service, "save_statement_import_record_db", fake_record
    )
    return state


class TestAlipayImport:
    def test_end_to_end_mapping(self, store):
        result = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )

        assert result.ok and result.detected_source == "alipay"
        assert result.imported_count == 6
        rows = store["inserted"][0][1]
        metro = next(r for r in rows if r["external_id"] == "ALI0001")
        assert metro["amount"] == -4.00
        assert metro["direction"] == "expense"
        assert metro["category"] == "transport"  # mapped from 交通出行
        assert metro["source"] == "alipay"
        refund = next(r for r in rows if r["external_id"] == "ALI0004_R1")
        assert refund["amount"] == 0.96
        assert refund["status"] == "refund"
        assert refund["category"] == "refund"
        assert refund["merchant_order_id"] == "ALI0004"  # refund_of linkage

    def test_skip_report_in_result(self, store):
        result = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )
        reasons = {
            s["reason_code"] for s in result.parse_report["skipped"]
        }

        assert {"credit_transfer", "failed_transaction", "zero_amount"} <= reasons

    def test_refund_of_closed_original_is_gated_out(self, store):
        result = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )

        inserted_ids = {r["external_id"] for r in store["inserted"][0][1]}
        # ALI0010 was 交易关闭 (never counted), so its refund must not import
        assert "ALI0010_R1" not in inserted_ids
        # ALI0004 was imported, so its partial refund imports normally
        assert "ALI0004_R1" in inserted_ids
        reasons = {s["reason_code"] for s in result.parse_report["skipped"]}
        assert "refund_original_not_imported" in reasons

    def test_quality_report_computed_and_persisted(self, store):
        result = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )

        report = result.quality_report
        assert report["source_type"] == "alipay"
        assert report["imported_count"] == result.imported_count
        assert report["skipped_by_reason"]["failed_transaction"] == 2
        assert any("failed" in w for w in report["warnings"])
        assert 0 <= report["category_confidence"] <= 1
        assert report["date_range"]["from"] <= report["date_range"]["to"]
        # persisted alongside the import record
        assert store["records"][-1]["quality_report"] == report

    def test_bank_wallet_settlement_warning(self):
        from app.connectors.statement_sources.contracts import ParseReport

        parse_report = ParseReport(
            detected_source="bank_icbc", encoding_or_format="pdf"
        )
        for i in range(3):
            parse_report.skip(i, "wallet_settlement", "row")

        report = statement_import_service._build_quality_report(
            report=parse_report, rows=[], duplicates=[], already_imported=0
        )

        assert any("wallet settlements" in w for w in report["warnings"])
        assert report["category_confidence"] is None

    def test_refund_anchored_to_previous_import_is_kept(self, store):
        # Original ALI0010 was imported in an earlier statement (e.g. as a
        # normal purchase before it was retroactively closed).
        store["external_ids"] = {"ALI0010"}

        result = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )

        inserted_ids = {r["external_id"] for r in store["inserted"][0][1]}
        assert "ALI0010_R1" in inserted_ids
        assert result.already_imported_count == 0


class TestWechatImport:
    def test_xlsx_import(self, store):
        result = statement_import_service.import_statement_file(
            user_id="demo", filename="wechat.xlsx", content=wechat_xlsx_bytes()
        )

        assert result.ok and result.detected_source == "wechat"
        assert result.imported_count == 4
        rows = store["inserted"][0][1]
        assert {r["source"] for r in rows} == {"wechat"}


class TestIdempotentReimport:
    def test_existing_external_ids_are_skipped(self, store):
        store["external_ids"] = {"ALI0001", "ALI0002"}

        result = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )

        assert result.already_imported_count == 2
        assert result.imported_count == 4
        inserted_ids = {r["external_id"] for r in store["inserted"][0][1]}
        assert "ALI0001" not in inserted_ids

    def test_full_reimport_inserts_nothing(self, store):
        first = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )
        store["external_ids"] = {
            r["external_id"] for r in store["inserted"][0][1] if r["external_id"]
        }
        store["inserted"].clear()

        second = statement_import_service.import_statement_file(
            user_id="demo", filename="alipay.csv", content=alipay_csv_bytes()
        )

        assert first.imported_count == 6
        assert second.imported_count == 0
        assert second.already_imported_count == 6
        assert not store["inserted"]  # nothing persisted on re-import


class TestCrossSourceDedup:
    def test_same_purchase_across_wallets_is_flagged(self, store):
        # Alipay 美团 328.00 on 2026-06-27 is already stored.
        store["window"] = [
            {
                "id": "42",
                "date": "2026-06-27",
                "amount": -328.0,
                "counterparty": "美团",
                "description": "烤肉店-美团App",
                "source": "alipay",
                "is_duplicate": False,
            }
        ]

        result = statement_import_service.import_statement_file(
            user_id="demo", filename="wechat.xlsx", content=wechat_xlsx_bytes()
        )

        assert len(result.duplicates) == 1
        dup = result.duplicates[0]
        assert dup["duplicate_of"] == "42"
        assert dup["reason"] == "cross_source_amount_date_counterparty"
        row = next(
            r for r in store["inserted"][0][1] if r["external_id"] == "WX0007"
        )
        assert row["is_duplicate"] is True
        assert row["duplicate_of"] == "42"

    def test_same_source_rows_are_not_deduped(self, store):
        store["window"] = [
            {
                "id": "43",
                "date": "2026-06-27",
                "amount": -328.0,
                "counterparty": "美团平台商户",
                "description": "烤肉店订单",
                "source": "wechat",  # same source: not a cross-source dup
                "is_duplicate": False,
            }
        ]

        result = statement_import_service.import_statement_file(
            user_id="demo", filename="wechat.xlsx", content=wechat_xlsx_bytes()
        )

        assert result.duplicates == []

    def test_card_tail_matches_bank_row_despite_name_mismatch(self, store):
        # Bank statements often show the acquirer (e.g. a person's name), not
        # the merchant: 山东水饺 in WeChat vs 赵俊苓 in the bank statement.
        from datetime import datetime
        from tests.statement_fixtures import WECHAT_HEADER  # noqa: F401

        store["window"] = [
            {
                "id": "77",
                "date": "2026-06-30",
                "amount": -28.8,
                "counterparty": "个人收单张老板",  # no name overlap with merchant
                "description": "消费-个人收单张老板",
                "source": "bank_icbc",
                "is_duplicate": False,
                "payment_method": "快捷支付",
                "external_id": "icbc:0001:2026-06-30T12:40:00:-28.80:100.00",
            }
        ]
        rows = [
            [datetime(2026, 6, 30, 12, 40, 33), "商户消费", "某餐饮公司", "堂食",
             "支出", 28.8, "某银行储蓄卡(0001)", "支付成功", "WXCARD1", "S1", "/"],
        ]

        result = statement_import_service.import_statement_file(
            user_id="demo", filename="w.xlsx", content=wechat_xlsx_bytes(rows)
        )

        assert len(result.duplicates) == 1
        assert result.duplicates[0]["reason"] == "card_paid_wallet_matches_bank"

    def test_card_tail_rule_requires_same_day(self, store):
        # Same amount on an adjacent day is NOT the same card transaction
        # (快捷支付 posts same-day): must not be flagged.
        from datetime import datetime

        store["window"] = [
            {
                "id": "78",
                "date": "2026-06-29",  # previous day
                "amount": -28.8,
                "counterparty": "个人收单张老板",
                "description": "消费-个人收单张老板",
                "source": "bank_icbc",
                "is_duplicate": False,
                "payment_method": "快捷支付",
                "external_id": "icbc:0001:2026-06-29T12:40:00:-28.80:100.00",
            }
        ]
        rows = [
            [datetime(2026, 6, 30, 12, 40, 33), "商户消费", "某餐饮公司", "堂食",
             "支出", 28.8, "某银行储蓄卡(0001)", "支付成功", "WXCARD2", "S2", "/"],
        ]

        result = statement_import_service.import_statement_file(
            user_id="demo", filename="w.xlsx", content=wechat_xlsx_bytes(rows)
        )

        assert result.duplicates == []

    def test_near_miss_amount_is_not_flagged(self, store):
        store["window"] = [
            {
                "id": "44",
                "date": "2026-06-27",
                "amount": -327.0,
                "counterparty": "美团",
                "description": "烤肉店-美团App",
                "source": "alipay",
                "is_duplicate": False,
            }
        ]

        result = statement_import_service.import_statement_file(
            user_id="demo", filename="wechat.xlsx", content=wechat_xlsx_bytes()
        )

        assert result.duplicates == []


@pytest.mark.asyncio
class TestImportRoute:
    async def test_generic_csv_route(self, store):
        upload = UploadFile(
            filename="statement.csv", file=BytesIO(GENERIC_CSV.encode("utf-8"))
        )

        result = await statement_import_route.import_statement(
            file=upload, user_id="demo"
        )

        assert result["ok"] is True
        assert result["imported_count"] == 2
        assert result["detected_source"] == "generic_csv"
        assert result["import_record"]["import_id"] == "imp_test"
        rows = store["inserted"][0][1]
        assert rows[1]["category"] == "Dining"  # explicit column passes through

    async def test_wechat_xlsx_route(self, store):
        upload = UploadFile(filename="bill.xlsx", file=BytesIO(wechat_xlsx_bytes()))

        result = await statement_import_route.import_statement(
            file=upload, user_id="demo"
        )

        assert result["ok"] is True
        assert result["detected_source"] == "wechat"

    async def test_rejects_unsupported_file(self, store):
        upload = UploadFile(filename="statement.pdf", file=BytesIO(b"not implemented"))

        result = await statement_import_route.import_statement(
            file=upload, user_id="demo"
        )

        assert result.status_code == 400
        assert store["records"][-1]["status"] == "failed"
