/**
 * Lightweight UI i18n (zh/en). The interface language is a client concern
 * stored in localStorage; the CFO's reply language is a separate profile
 * preference consumed by the backend composer.
 */
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type UiLang = "zh" | "en";

const STORAGE_KEY = "findesk-lang";

const translations: Record<string, { zh: string; en: string }> = {
  // topbar / navigation
  "nav.workspace": { zh: "财务工作台", en: "Finance Workspace" },
  "nav.office": { zh: "My Office", en: "My Office" },
  "nav.settings": { zh: "设置", en: "Settings" },

  // hero
  "hero.eyebrow": { zh: "CFO 简报", en: "CFO BRIEF" },
  "hero.audit.verified": { zh: "审计通过", en: "Audit verified" },
  "hero.audit.needs_review": { zh: "审计关注", en: "Audit flagged" },
  "hero.audit.data_limited": { zh: "数据有限", en: "Data limited" },
  "hero.fallback": {
    zh: "导入账单后，CFO 会在这里给出本月的判断和最优先的行动。",
    en: "Import a statement and the CFO's monthly judgment will appear here.",
  },
  "hero.stat.expense": { zh: "本月支出", en: "Monthly spend" },
  "hero.stat.income": { zh: "本月收入", en: "Monthly income" },
  "hero.stat.budget": { zh: "预算状态", en: "Budget status" },
  "hero.askCfo": { zh: "问 CFO", en: "Ask CFO" },
  "hero.upload": { zh: "上传账单", en: "Upload statement" },
  "hero.uploading": { zh: "上传中", en: "Uploading" },
  "hero.uploadHint": { zh: "支持支付宝 / 微信 / 银行流水", en: "Alipay / WeChat / bank statements" },

  // budget status values
  "budget.good": { zh: "良好", en: "good" },
  "budget.watch": { zh: "观察", en: "watch" },
  "budget.risk": { zh: "风险", en: "risk" },
  "budget.data_limited": { zh: "数据不足", en: "data limited" },

  // action center
  "actions.title": { zh: "行动中心", en: "Action Center" },
  "actions.fromBrief": { zh: "来自 CFO 简报", en: "From CFO brief" },
  "actions.onboarding": { zh: "入门提示", en: "Onboarding hints" },
  "actions.viewDetails": { zh: "查看明细 →", en: "View details →" },
  "actions.askDay.title": { zh: "花了", en: "spent" },
  "actions.askDay.body": {
    zh: "这是本月最高的单日支出。想让 CFO 逐笔解释这一天吗？",
    en: "This is the highest spending day this month. Want the CFO to walk through it?",
  },
  "actions.askDay.cta": { zh: "问 CFO 这一天 →", en: "Ask the CFO about this day →" },

  // explore tabs
  "tabs.calendar": { zh: "日历", en: "Calendar" },
  "tabs.trends": { zh: "趋势", en: "Trends" },
  "tabs.categories": { zh: "分类", en: "Categories" },
  "tabs.transactions": { zh: "交易", en: "Transactions" },

  // footer coverage
  "coverage.range": { zh: "数据覆盖", en: "Data coverage" },
  "coverage.rows": { zh: "笔", en: "rows" },
  "coverage.duplicates": { zh: "笔跨源重复已排除", en: "cross-source duplicates excluded" },
  "coverage.latestImport": { zh: "最近导入", en: "Latest import" },
  "coverage.none": { zh: "尚未导入", en: "none yet" },

  // sources (user-side naming, never system codes)
  "source.bank_icbc": { zh: "工商银行", en: "ICBC" },
  "source.alipay": { zh: "支付宝", en: "Alipay" },
  "source.wechat": { zh: "微信", en: "WeChat" },
  "source.generic_csv": { zh: "CSV 导入", en: "CSV import" },
  "source.manual": { zh: "手动", en: "manual" },

  // misc workspace
  "workspace.loading": { zh: "加载中…", en: "Loading…" },
  "workspace.retry": { zh: "重试", en: "Retry" },

  // settings
  "settings.uiLanguage": { zh: "界面语言", en: "Interface language" },
  "settings.uiLanguage.note": {
    zh: "只影响界面文字；CFO 回复语言在下方单独设置。",
    en: "Affects interface text only; the CFO's reply language is set separately below.",
  },
};

type I18nValue = {
  lang: UiLang;
  setLang: (lang: UiLang) => void;
  t: (key: string) => string;
};

const I18nContext = createContext<I18nValue>({
  lang: "zh",
  setLang: () => {},
  t: (key) => key,
});

function detectLang(): UiLang {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "zh" || stored === "en") return stored;
  return navigator.language?.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<UiLang>(detectLang);

  const setLang = useCallback((next: UiLang) => {
    localStorage.setItem(STORAGE_KEY, next);
    setLangState(next);
  }, []);

  const t = useCallback(
    (key: string) => translations[key]?.[lang] ?? key,
    [lang]
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
