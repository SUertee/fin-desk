export type SummaryStatus = "neutral" | "good" | "watch" | "risk";
export type EffortLevel = "low" | "medium" | "high";
export type ImpactLevel = "low" | "medium" | "high";
export type AuditStatus = "verified" | "needs_review" | "data_limited";

export type SummaryCard = {
  label: string;
  value: string;
  status?: SummaryStatus;
  note?: string | null;
};

export type AgentFinding = {
  agent: string;
  title: string;
  evidence: string[];
};

export type AgentAction = {
  title: string;
  rationale: string;
  effort: EffortLevel;
  impact: ImpactLevel;
};

export type AgentAudit = {
  confidence: number;
  status: AuditStatus;
  warnings: string[];
};

export type FinanceAgentData = {
  summary_cards?: SummaryCard[] | null;
  findings?: AgentFinding[] | null;
  actions?: AgentAction[] | null;
  audit?: AgentAudit | null;
};

export type ChatResponse = {
  reply: string;
  agent_used?: string | null;
  data?: FinanceAgentData | null;
};
