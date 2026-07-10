"""Anonymized statement fixtures mirroring real Alipay/WeChat export layouts.

Structures (preamble shape, header names, status vocabulary, refund order-id
linkage) match real June 2026 exports; names, phone numbers, and order ids are
fabricated.
"""

from __future__ import annotations

import io


ALIPAY_PREAMBLE = """------------------------------------------------------------------------------------
导出信息：
姓名：张三
支付宝账户：13800000000
起始时间：[2026-06-01 00:00:00]    终止时间：[2026-06-30 23:59:59]
导出交易类型：[全部]
导出时间：[2026-07-04 13:03:08]
共10笔记录
收入：0笔 0.00元
支出：4笔 445.99元
不计收支：6笔 4106.13元

特别提示：
5.部分账单如：充值提现、账户转存或者个人设置收支等不计入为收入或者支出，记为不计收支类；

------------------------支付宝支付科技有限公司  电子客户回单------------------------
"""

ALIPAY_HEADER = "交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注,"

ALIPAY_ROWS = [
    # normal expenses
    "2026-06-30 20:28:35,交通出行,上海公共交通卡股份有限公司,zfb***@sptcc.com,上海地铁-A站-B站,支出,4.00,花呗,交易成功,ALI0001\t,M0001\t,,",
    "2026-06-28 19:59:44,餐饮美食,叮咚买菜,fin***@100.me,叮咚买菜-260628,支出,104.34,花呗,交易成功,ALI0002\t,M0002\t,,",
    "2026-06-27 13:27:03,餐饮美食,美团,zxp***@meituan.com,烤肉店-美团App,支出,328.00,花呗,交易成功,ALI0003\t,M0003\t,,",
    # expense later partially refunded (parent of ALI0004_R1)
    "2026-06-13 21:45:03,餐饮美食,叮咚买菜,fin***@100.me,叮咚买菜-260613,支出,9.65,花呗,交易成功,ALI0004\t,M0004\t,,",
    # partial refund linked to ALI0004 via underscore parent
    "2026-06-14 05:47:14,退款,叮咚买菜,fin***@100.me,退款-叮咚买菜-260613,不计收支,0.96,花呗,退款成功,ALI0004_R1\t,M0004R\t,,",
    # credit repayment success + failed attempts (transfers, never spending)
    "2026-06-10 19:13:05,信用借还,花呗,/,花呗自动还款-2026年06月账单,不计收支,1984.87,中国工商银行储蓄卡(0001),还款成功,ALI0005\t,\t,,",
    "2026-06-10 09:20:58,信用借还,花呗,/,花呗自动还款,不计收支,1984.87,,还款失败,ALI0006\t,\t,,",
    "2026-06-09 16:30:58,信用借还,花呗,/,花呗自动还款,不计收支,1984.87,,还款失败,ALI0007\t,\t,,",
    # 余额宝 interest
    "2026-06-08 03:25:43,投资理财,余额宝-快线宝,/,余额-2026.06.07-收益发放,不计收支,0.01,余额,交易成功,ALI0008\t,\t,,",
    # zero-amount promo row
    "2026-06-17 14:06:42,交通出行,哈啰单车,zij***@hellobike.com,哈啰骑行卡免费领取,支出,0.00,哈啰骑行卡,交易成功,ALI0009\t,\t,,",
    # fully-refunded purchase retroactively marked 交易关闭 (excluded from
    # Alipay's own expense summary) plus its refund row: the refund must be
    # gated out at import because its original was never counted
    "2026-06-02 12:35:33,日用百货,罗森便利店,law***@lawson.com.cn,支付宝门店购物,支出,21.40,花呗,交易关闭,ALI0010\t,M0010\t,,",
    "2026-06-03 09:56:42,日用百货,罗森便利店,law***@lawson.com.cn,退款-支付宝门店购物,不计收支,21.40,花呗,退款成功,ALI0010_R1\t,M0010R\t,,",
    # investment transfer into own account: not interest income
    "2026-06-05 15:18:16,投资理财,黄金,/,黄金-本月定额买入转入,不计收支,500.00,中国工商银行储蓄卡(0001),交易成功,ALI0011\t,\t,,",
]


def alipay_csv_bytes(rows: list[str] | None = None) -> bytes:
    body = ALIPAY_PREAMBLE + ALIPAY_HEADER + "\n" + "\n".join(rows or ALIPAY_ROWS) + "\n"
    return body.encode("gb18030")


WECHAT_PREAMBLE_ROWS = [
    ["微信支付账单明细"],
    ["微信昵称：[测试]"],
    ["起始时间：[2026-06-01 00:00:00] 终止时间：[2026-06-30 23:59:59]"],
    ["导出类型：[全部]"],
    ["共8笔记录"],
    ["注："],
    ["1. 充值/提现/理财通购买/零钱通存取/信用卡还款等交易，将计入中性交易"],
    ["----------------------微信支付账单明细列表--------------------"],
]

WECHAT_HEADER = [
    "交易时间", "交易类型", "交易对方", "商品", "收/支",
    "金额(元)", "支付方式", "当前状态", "交易单号", "商户单号", "备注",
]


def default_wechat_rows() -> list[list[object]]:
    from datetime import datetime

    return [
        [datetime(2026, 6, 30, 12, 40, 33), "商户消费", "某餐饮公司", "【堂食】门店A", "支出", 28.8, "零钱", "支付成功", "WX0001", "S0001", "/"],
        [datetime(2026, 6, 30, 8, 34, 12), "商户消费", "智能物业", "水电费:100.00元", "支出", 100, "某银行储蓄卡(0001)", "支付成功", "WX0002", "S0002", "/"],
        # fully refunded transfer pair: both sides must be excluded
        [datetime(2026, 6, 27, 16, 15, 12), "转账-退款", "/", "转账备注:微信转账", "收入", 500, "某银行储蓄卡(0001)", "已全额退款", "WX0003", None, "/"],
        [datetime(2026, 6, 26, 16, 15, 10), "转账", "亲属A", "转账备注:微信转账", "支出", 500, "某银行储蓄卡(0001)", "已全额退款", "WX0004", "S0004", "/"],
        # income
        [datetime(2026, 6, 5, 16, 4, 33), "转账", "亲属A", "转账备注:微信转账", "收入", 3000, "零钱", "已存入零钱", "WX0005", "S0005", "/"],
        # neutral top-up
        [datetime(2026, 6, 5, 20, 13, 48), "零钱充值", "某银行(0001)", "/", "/", 500, "某银行储蓄卡(0001)", "充值完成", "WX0006", "S0006", "/"],
        # cross-source duplicate of the Alipay 美团 328 purchase (same day)
        [datetime(2026, 6, 27, 13, 30, 0), "商户消费", "美团平台商户", "烤肉店订单", "支出", 328, "零钱", "支付成功", "WX0007", "S0007", "/"],
    ]


def wechat_xlsx_bytes(rows: list[list[object]] | None = None) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for preamble_row in WECHAT_PREAMBLE_ROWS:
        sheet.append(preamble_row)
    sheet.append(WECHAT_HEADER)
    for row in rows if rows is not None else default_wechat_rows():
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


GENERIC_CSV = """date,description,amount,currency,category
2026-06-01,Salary,25000,CNY,Income
2026-06-02,Cafe,-38.5,CNY,Dining
"""


# Text layout as extracted by pypdf from a real ICBC history PDF: date on its
# own line, wrapped counterparty/summary names, page footer glued to the last
# record of a page.
ICBC_PDF_TEXT = """请扫描二维码
识别明细真伪
中国工商银行借记账户历史明细（电子版）
卡号 6215000000000000001 户名：张三 起止日期：2026-06-01 — 2026-06-30
交易日期 账号 储种 序号 币种 钞汇 摘要 地区 收入/支出金额 余额 对方户名 对方账号 渠道
2026-06-02
10:14:29 1102270000000000001 活期 00000 人民币 钞 消费 1102 -69.00 1123.23 支付宝（中国）网络技术有限公司 2155****0690 快捷支付
2026-06-03
07:02:01 1102270000000000001 活期 00000 人民币 钞 消费 1102 -55.23 1068.00 北京佳美惠邻超市
管理有限公司 1200****4229 快捷支付
2026-06-05
21:11:31 1102270000000000001 活期 00000 人民币 钞 消费 1102 -92.00 976.00 深圳市财付通支付
科技有限公司 2433****0133 快捷支付
2026-06-08
09:00:00 1102270000000000001 活期 00000 人民币 钞 他行汇入 1102 +8,384.82 9,360.82 上海某科技 有限公司 640206694 其他
2026-06-10
12:00:00 1102270000000000001 活期 00000 人民币 钞 微信零钱提 现 1102 +300.00 9,660.82 张三 1184****6333 快捷支付
2026-06-12
08:30:00 1102270000000000001 活期 00000 人民币 钞 退款 1102 +38.40 9,699.22 京东商城业务 8151****M0BQ 快捷支付
2026-06-21
23:59:59 1102270000000000001 活期 00000 人民币 钞 利息 1102 +0.23 9,699.45 （空） （空） 批量业务 本页支出算术合计：216.23 本页交易笔数：7 本页收入算术合计：8,723.45 下单时间：2026-07-04 19:52:28 中国工商银行 56689737 2026-07-04
19:52:28 1742A6FCF026
"""
