"""
categorizer.py
- Deterministic transaction categorization using regex rules.
- We return both category and confidence for explainability.
"""

import re
from typing import Tuple

# Regex rules: (pattern, category). First match wins, so more specific
# Chinese merchant/keyword rules come before the generic English ones.
# Derived from real Alipay/WeChat/ICBC statement counterparties.
CATEGORY_RULES = [
    # -- Chinese: groceries / convenience (before dining: 买菜 vs 菜) --
    (r"(买菜|超市|便利|生鲜|水果|菜场|集市|盒马|山姆|叮咚|罗森|lawson|全家|好德|快客|便利蜂)", "groceries"),
    # -- Chinese: transport --
    (
        r"(地铁|公交|交通卡|公共交通|出行|打车|叫车|滴滴|高德|曹操|如祺|摩拜|哈啰|单车|骑行|加油|停车|铁路|12306|火车票|机票|航空)",
        "transport",
    ),
    # -- Chinese: utilities / telecom --
    (r"(水电|电费|水费|燃气|物业|宽带|话费|智电|中国移动|中国联通|中国电信)", "utilities"),
    # -- Chinese: housing --
    (r"(房租|房东|租房|公寓|租金)", "housing"),
    # -- Chinese: health --
    (r"(药房|药店|医院|诊所|口腔|体检|眼镜|医疗)", "health"),
    # -- Chinese: travel --
    (r"(酒店|民宿|携程|同程|去哪儿|航班|旅游|trip\.com)", "travel"),
    # -- Chinese: entertainment / fitness --
    (r"(电影|影城|影院|剧院|ktv|游戏|steam|网吧|健身|训练馆|球馆|演出|门票|文化休闲)", "entertainment"),
    # -- Chinese: dining — platforms and merchants --
    (
        r"(美团|三快|汉海|饿了么|口碑|肯德基|kfc|麦当劳|mcd|必胜客|汉堡|德克士|咖啡|cotti|库迪|瑞幸|luckin|星巴克|"
        r"奶茶|喜茶|蜜雪|茶百道|霸王茶姬|大米先生|老盛昌|韩宫宴|巴比|沙县|曼玲|超模厨房|早安山丘|三明治|烘焙|面包|蛋糕|酸奶|"
        r"谷麦香|陈香贵|小面|健康菜)",
        "dining",
    ),
    # -- Chinese: dining — generic food words --
    (
        r"(餐饮|餐厅|饭店|美食|小吃|面馆|面店|粥店|汤包|馄饨|水饺|饺子|包子|煎饼|灌饼|烧烤|火锅|麻辣|轻食|沙拉|食品|食堂|快餐|茶餐)",
        "dining",
    ),
    # -- Chinese: shopping / e-commerce (网银在线 acquires JD payments) --
    (r"(淘宝|天猫|拼多多|京东|网银在线|唯品会|得物|抖音|小红书|优衣库|百货|数码|电器|服饰)", "shopping"),
    # -- Chinese: subscriptions / digital services --
    (r"(deepseek|minimax|稀宇|api充值|阿里云|腾讯云|会员月卡|连续包月)", "services"),
    # -- Chinese: transfers / red packets --
    (r"(转账|红包)", "transfer"),
    # -- English fallbacks --
    (r"(coles|woolworths|aldi|iga|market|grocery)", "groceries"),
    (r"(uber|ola|didi|taxi|opal|train|bus|metro)", "transport"),
    (
        r"(mr coconut|monster curry|cafe|restaurant|joe'?s|food|eat|bar|bistro)",
        "dining",
    ),
    (
        r"(billi|electric|gas|water|utility|internet|telstra|optus|vodafone)",
        "utilities",
    ),
    (r"(rent|landlord|strata|mortgage)", "housing"),
    (r"(interest|fee|international transaction fee|charge)", "fees_interest"),
    (r"(transfer|fast transfer|payid)", "transfer"),
]


def rule_categorize(description: str) -> Tuple[str, float]:
    """
    Categorize a transaction description via regex rules.

    Returns:
        (category, confidence)
    """
    text = (description or "").lower()
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, text):
            return category, 0.85
    return "other", 0.30


def enrich_transactions(transactions: list[dict]) -> list[dict]:
    """
    Add category + confidence to each transaction.
    This keeps the LLM stage cleaner and more reliable.
    """
    enriched = []
    for t in transactions:
        desc = t.get("description", "")
        cat, conf = rule_categorize(desc)
        enriched.append({**t, "category": cat, "cat_confidence": conf})
    return enriched
