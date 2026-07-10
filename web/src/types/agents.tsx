import type { ReactNode } from "react";
import {
  BadgeCheck,
  ChartNoAxesCombined,
  ClipboardCheck,
  Landmark,
  LineChart,
} from "lucide-react";

export type AgentType =
  | "cfo"
  | "expense_analyst"
  | "budget_coach"
  | "auditor"
  | "market_scout";

export type AgentMeta = {
  id: AgentType;
  label: string;
  shortLabel: string;
  summary: string;
  // Typed routing hint honored by runtime policy (additive, never bypasses audit)
  requestedSpecialist?: "expense_analyst" | "budget_coach";
  badgeClass: string;
  icon: ReactNode;
};

export const AGENTS: AgentMeta[] = [
  {
    id: "cfo",
    label: "CFO",
    shortLabel: "CFO",
    summary: "统一入口，协调团队并输出优先级决策。",
    badgeClass: "bg-[#172026] text-white",
    icon: <Landmark className="h-4 w-4" />,
  },
  {
    id: "expense_analyst",
    label: "Expense Analyst",
    shortLabel: "Expense",
    summary: "分析支出结构、类别变化、异常和重复交易。",
    requestedSpecialist: "expense_analyst",
    badgeClass: "bg-[#4b8078] text-white",
    icon: <ChartNoAxesCombined className="h-4 w-4" />,
  },
  {
    id: "budget_coach",
    label: "Budget Coach",
    shortLabel: "Budget",
    summary: "把预算压力转成低摩擦行动和提醒规则。",
    requestedSpecialist: "budget_coach",
    badgeClass: "bg-[#6f7f62] text-white",
    icon: <ClipboardCheck className="h-4 w-4" />,
  },
  {
    id: "auditor",
    label: "Auditor",
    shortLabel: "Audit",
    summary: "检查证据、风险、过度自信和数据限制。",
    badgeClass: "bg-[#5f6f78] text-white",
    icon: <BadgeCheck className="h-4 w-4" />,
  },
  {
    id: "market_scout",
    label: "Market Scout",
    shortLabel: "Market",
    summary: "提供轻量市场和宏观背景，保持风险克制。",
    badgeClass: "bg-[#7b6f58] text-white",
    icon: <LineChart className="h-4 w-4" />,
  },
];
