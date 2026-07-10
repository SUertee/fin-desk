"""Parser and detection tests for dedicated statement sources."""

import pytest

from app.connectors.statement_sources import (
    StatementImportError,
    detect_source,
    parse_alipay_csv,
    parse_generic_csv,
    parse_wechat_xlsx,
)
from app.connectors.statement_sources.icbc_pdf import parse_icbc_text
from tests.statement_fixtures import (
    GENERIC_CSV,
    ICBC_PDF_TEXT,
    alipay_csv_bytes,
    wechat_xlsx_bytes,
)


class TestAlipayParser:
    def test_parses_gb18030_with_preamble(self):
        transactions, report = parse_alipay_csv(alipay_csv_bytes())

        assert report.detected_source == "alipay"
        assert report.encoding_or_format == "gb18030"
        assert report.total_rows == 13
        assert report.parsed_rows == len(transactions) == 7

    def test_expense_signs_and_fields(self):
        transactions, _ = parse_alipay_csv(alipay_csv_bytes())
        metro = next(t for t in transactions if t.source_reference == "ALI0001")

        assert metro.amount == -4.00
        assert metro.date == "2026-06-30"
        assert metro.counterparty == "上海公共交通卡股份有限公司"
        assert metro.payment_method == "花呗"
        assert metro.raw_category == "交通出行"
        assert metro.status == "completed"
        assert metro.currency == "CNY"

    def test_refund_is_positive_and_linked_to_parent(self):
        transactions, _ = parse_alipay_csv(alipay_csv_bytes())
        refund = next(t for t in transactions if t.source_reference == "ALI0004_R1")

        assert refund.status == "refund"
        assert refund.amount == 0.96
        assert refund.refund_of == "ALI0004"

    def test_interest_rows_import_as_income(self):
        transactions, _ = parse_alipay_csv(alipay_csv_bytes())
        interest = next(t for t in transactions if t.status == "interest")

        assert interest.amount == 0.01

    def test_credit_transfers_failed_and_zero_rows_are_skipped(self):
        _, report = parse_alipay_csv(alipay_csv_bytes())
        reasons = report.skipped_by_reason()

        assert reasons["credit_transfer"] == 1  # 还款成功 transfer
        assert reasons["failed_transaction"] == 2  # 还款失败 attempts
        assert reasons["zero_amount"] == 1
        assert reasons["closed_transaction"] == 1  # 交易关闭 purchase
        assert reasons["investment_transfer"] == 1  # 黄金转入, not interest

    def test_investment_transfer_is_not_interest_income(self):
        transactions, _ = parse_alipay_csv(alipay_csv_bytes())
        interest = [t for t in transactions if t.status == "interest"]

        assert [t.amount for t in interest] == [0.01]  # 收益发放 only, no 转入

    def test_netting_reproduces_statement_expense_summary(self):
        transactions, _ = parse_alipay_csv(alipay_csv_bytes())
        expenses = sum(-t.amount for t in transactions if t.amount < 0)

        assert expenses == pytest.approx(445.99)

    def test_missing_header_raises(self):
        with pytest.raises(StatementImportError):
            parse_alipay_csv("垃圾数据\n没有表头\n".encode("gb18030"))


class TestWechatParser:
    def test_parses_xlsx_with_preamble(self):
        transactions, report = parse_wechat_xlsx(wechat_xlsx_bytes())

        assert report.detected_source == "wechat"
        assert report.encoding_or_format == "xlsx"
        assert report.total_rows == 7
        assert report.parsed_rows == len(transactions) == 4

    def test_native_types_and_signs(self):
        transactions, _ = parse_wechat_xlsx(wechat_xlsx_bytes())
        dining = next(t for t in transactions if t.source_reference == "WX0001")
        income = next(t for t in transactions if t.source_reference == "WX0005")

        assert dining.amount == -28.8
        assert dining.date == "2026-06-30"
        assert dining.payment_method == "零钱"
        assert income.amount == 3000

    def test_fully_refunded_pair_is_excluded_on_both_sides(self):
        transactions, report = parse_wechat_xlsx(wechat_xlsx_bytes())
        refs = {t.source_reference for t in transactions}

        assert "WX0003" not in refs and "WX0004" not in refs
        assert report.skipped_by_reason()["fully_refunded_pair"] == 2

    def test_neutral_topup_is_skipped(self):
        transactions, report = parse_wechat_xlsx(wechat_xlsx_bytes())

        assert "WX0006" not in {t.source_reference for t in transactions}
        assert report.skipped_by_reason()["neutral_transfer"] == 1

    def test_totals_match_statement_summary_minus_refund_pair(self):
        transactions, _ = parse_wechat_xlsx(wechat_xlsx_bytes())
        expense = sum(-t.amount for t in transactions if t.amount < 0)
        income = sum(t.amount for t in transactions if t.amount > 0)

        assert expense == pytest.approx(28.8 + 100 + 328)
        assert income == pytest.approx(3000)

    def test_invalid_xlsx_raises(self):
        with pytest.raises(StatementImportError):
            parse_wechat_xlsx(b"PK\x03\x04 not a real workbook")


class TestIcbcParser:
    def test_parses_wrapped_records_and_preamble(self):
        transactions, report = parse_icbc_text(ICBC_PDF_TEXT)

        assert report.detected_source == "bank_icbc"
        assert report.total_rows == 7
        assert report.parsed_rows == len(transactions) == 4

    def test_wallet_settlements_are_skipped(self):
        _, report = parse_icbc_text(ICBC_PDF_TEXT)
        reasons = report.skipped_by_reason()

        # Alipay + Tenpay pass-through rows never double-count wallet bills
        assert reasons["wallet_settlement"] == 2
        assert reasons["own_transfer"] == 1  # 微信零钱提现 (wrapped 摘要)

    def test_wrapped_counterparty_name_is_joined(self):
        transactions, _ = parse_icbc_text(ICBC_PDF_TEXT)
        market = next(t for t in transactions if t.amount == -55.23)

        assert market.counterparty == "北京佳美惠邻超市管理有限公司"
        assert market.raw_category == "消费"

    def test_income_refund_interest_classification(self):
        transactions, _ = parse_icbc_text(ICBC_PDF_TEXT)
        salary = next(t for t in transactions if t.raw_category == "他行汇入")
        refund = next(t for t in transactions if t.status == "refund")
        interest = next(t for t in transactions if t.status == "interest")

        assert salary.amount == 8384.82  # comma-thousands parsed
        assert refund.amount == 38.40 and refund.counterparty == "京东商城业务"
        assert interest.amount == 0.23 and interest.counterparty is None
        assert "下单时间" not in (interest.description or "")

    def test_references_are_unique_and_stable(self):
        first, _ = parse_icbc_text(ICBC_PDF_TEXT)
        second, _ = parse_icbc_text(ICBC_PDF_TEXT)

        refs = [t.source_reference for t in first]
        assert len(refs) == len(set(refs))
        assert refs == [t.source_reference for t in second]


class TestDetection:
    def test_detects_alipay_from_gb18030_preamble(self):
        assert detect_source("bill.csv", alipay_csv_bytes()) == "alipay"

    def test_detects_wechat_from_xlsx_magic(self):
        assert detect_source("bill.xlsx", wechat_xlsx_bytes()) == "wechat_xlsx"

    def test_detects_icbc_from_pdf_magic(self):
        assert detect_source("流水.pdf", b"%PDF-1.7 ...") == "icbc_pdf"

    def test_generic_csv_falls_through(self):
        assert detect_source("bill.csv", GENERIC_CSV.encode("utf-8")) == "generic_csv"


class TestGenericParser:
    def test_generic_csv_still_parses(self):
        transactions, report = parse_generic_csv(GENERIC_CSV)

        assert report.detected_source == "generic_csv"
        assert transactions[0].amount == 25000
        assert transactions[0].raw_category == "Income"
        assert transactions[1].amount == -38.5

    def test_income_expense_column_pair(self):
        transactions, _ = parse_generic_csv(
            "交易时间,交易对方,收入,支出,币种\n2026/06/03,餐厅,,88.8,CNY\n2026/06/04,退款,20,,CNY\n"
        )

        assert transactions[0].amount == -88.8
        assert transactions[0].counterparty == "餐厅"
        assert transactions[1].amount == 20

    def test_raises_when_no_valid_rows(self):
        with pytest.raises(StatementImportError):
            parse_generic_csv("date,description\nbad,Cafe\n")
