"""Categorizer rule tests, focused on Chinese merchant coverage."""

import pytest

from app.services.categorizer import rule_categorize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # groceries / convenience
        ("叮咚买菜-2606282109609847892", "groceries"),
        ("罗森(祁华路店)", "groceries"),
        ("北京佳美惠邻超市管理有限公司", "groceries"),
        # transport
        ("上海公共交通卡股份有限公司", "transport"),
        ("高德打车订单", "transport"),
        ("哈啰单车月卡", "transport"),
        ("北京摩拜科技有限公司", "transport"),
        # dining: platforms and merchants
        ("北京三快在线科技有限公司", "dining"),
        ("美团平台商户 烤肉店订单", "dining"),
        ("巴比祁华路店", "dining"),
        ("老盛昌汤包", "dining"),
        ("沙县小吃（祁华路店）", "dining"),
        ("COTTICOFFEE库迪咖啡", "dining"),
        ("鸡蛋灌饼545", "dining"),
        # shopping
        ("网银在线（北京）支付科技有限公司", "shopping"),
        ("拼多多平台商户", "shopping"),
        # utilities / housing / health
        ("智电生态 水电费:100.00元", "utilities"),
        ("宝祈雅苑房东 邓姐", "housing"),
        ("上海益丰大药房", "health"),
        # entertainment / travel
        ("燃Plus综合训练馆（宝山日月光店）", "entertainment"),
        ("上海如程酒店北京师范大学店", "travel"),
        # unmatched stays other
        ("完全未知的商户XYZ", "other"),
    ],
)
def test_chinese_rules(text, expected):
    category, confidence = rule_categorize(text)
    assert category == expected
    assert confidence == (0.30 if expected == "other" else 0.85)


def test_groceries_wins_over_dining_for_grocery_platforms():
    # 买菜 platforms must not fall into the generic dining words
    assert rule_categorize("叮咚买菜 生鲜")[0] == "groceries"


def test_english_rules_still_work():
    assert rule_categorize("Uber trip")[0] == "transport"
    assert rule_categorize("Woolworths grocery")[0] == "groceries"
