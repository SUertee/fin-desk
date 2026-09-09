import type { UiLang } from "../i18n";

const CATEGORY_LABELS: Record<string, { zh: string; en: string }> = {
  housing: { zh: "住房房租", en: "Housing" },
  food: { zh: "餐饮", en: "Food" },
  dining: { zh: "餐饮", en: "Dining" },
  food_dining: { zh: "餐饮", en: "Food & dining" },
  groceries: { zh: "买菜日用", en: "Groceries" },
  transport: { zh: "交通出行", en: "Transport" },
  transportation: { zh: "交通出行", en: "Transportation" },
  shopping: { zh: "购物", en: "Shopping" },
  healthcare: { zh: "医疗健康", en: "Healthcare" },
  health: { zh: "医疗健康", en: "Health" },
  entertainment: { zh: "休闲娱乐", en: "Entertainment" },
  personal_care: { zh: "个护美容", en: "Personal care" },
  utilities: { zh: "水电通信", en: "Utilities" },
  subscription: { zh: "订阅服务", en: "Subscriptions" },
  subscriptions: { zh: "订阅服务", en: "Subscriptions" },
  education: { zh: "学习教育", en: "Education" },
  travel: { zh: "旅行", en: "Travel" },
  transfer: { zh: "转账", en: "Transfer" },
  income: { zh: "收入", en: "Income" },
  salary: { zh: "工资", en: "Salary" },
  refund: { zh: "退款", en: "Refund" },
  other: { zh: "其他", en: "Other" },
  uncategorized: { zh: "待分类", en: "Uncategorized" },
};

const SOURCE_LABELS: Record<string, { zh: string; en: string }> = {
  bank_icbc: { zh: "工商银行", en: "ICBC" },
  icbc: { zh: "工商银行", en: "ICBC" },
  alipay: { zh: "支付宝", en: "Alipay" },
  wechat: { zh: "微信", en: "WeChat" },
  generic_csv: { zh: "CSV 导入", en: "CSV import" },
  manual: { zh: "手动记录", en: "Manual" },
};

export function financeCategoryLabel(value: string | null | undefined, lang: UiLang = "zh") {
  const raw = (value || "uncategorized").trim();
  const known = CATEGORY_LABELS[raw.toLowerCase()];
  return known?.[lang] ?? raw;
}

export function financeSourceLabel(value: string | null | undefined, lang: UiLang = "zh") {
  const raw = (value || "manual").trim();
  const known = SOURCE_LABELS[raw.toLowerCase()];
  return known?.[lang] ?? raw;
}
