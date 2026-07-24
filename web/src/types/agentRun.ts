export type AgentRunUsage = {
  request_count: number;
  model_response_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type DecimalString = string;

export type MoneyAmount = {
  amount: DecimalString;
  currency: string;
};

export type ExchangeRateSnapshot = {
  billing_currency: string;
  reporting_currency: string;
  exchange_rate: DecimalString;
  exchange_rate_date: string;
  exchange_rate_source: string;
};

export type ModelPricing = {
  profile: string;
  provider: string;
  model_name: string;
  billing_currency: string;
  input_cost_per_1m: DecimalString;
  output_cost_per_1m: DecimalString;
  pricing_source: string;
  pricing_effective_date: string;
};

export type LLMStageCost = {
  stage: string;
  status: string;
  profile: string;
  provider?: string | null;
  model_name?: string | null;
  usage: AgentRunUsage;
  pricing?: ModelPricing | null;
  billing_input_cost?: MoneyAmount | null;
  billing_output_cost?: MoneyAmount | null;
  billing_total?: MoneyAmount | null;
  reporting_total?: MoneyAmount | null;
  exchange_rate_snapshot?: ExchangeRateSnapshot | null;
  issues: Array<
    | "missing_pricing"
    | "missing_exchange_rate"
    | "historical_v1_detail_unavailable"
  >;
};

export type AgentRunCost = {
  status: "complete" | "partial" | "not_applicable";
  issues: LLMStageCost["issues"];
  reporting_currency: string;
  billing_totals: MoneyAmount[];
  reporting_total?: MoneyAmount | null;
  stages: LLMStageCost[];
};

export type AgentToolCall = {
  name: string;
  status: "expected" | "called" | "failed";
  agent?: string | null;
  latency_ms?: number | null;
};

export type AgentHandoff = {
  from_agent: string;
  to_agent: string;
  status: "planned" | "completed" | "failed";
  reason?: string | null;
};

export type AgentOutputValidation = {
  agent: string;
  contract: string;
  status: "passed" | "failed";
  errors: string[];
};

export type AgentRunSummary = {
  request_id: string;
  user_id: string;
  entrypoint: "chat" | "workspace_brief";
  runtime_requested: string;
  runtime_used?: string | null;
  model_name?: string | null;
  output_contract?: string | null;
  audit_status?: string | null;
  error_type?: string | null;
  usage: AgentRunUsage;
  cost?: AgentRunCost;
  created_at?: string;
};

export type AgentRunPagination = {
  limit: number;
  offset: number;
  has_more: boolean;
  next_offset?: number | null;
  previous_offset?: number | null;
};

export type AgentRunListResponse = {
  runs: AgentRunSummary[];
  pagination: AgentRunPagination;
};

export type AgentRunTimelineItem = {
  kind: "agent_selected" | "tool_call" | "handoff" | "validation";
  label: string;
  status?: string | null;
  agent?: string | null;
  reason?: string | null;
  latency_ms?: number | null;
  errors?: string[];
};

export type AgentRunProjection = {
  summary: {
    request_id: string;
    entrypoint: "chat" | "workspace_brief";
    user_id: string;
    runtime_requested: string;
    runtime_used?: string | null;
    model_name?: string | null;
    selected_agents: string[];
    output_contract?: string | null;
    audit_status?: string | null;
    latency_ms: number;
    error_type?: string | null;
  };
  timeline: AgentRunTimelineItem[];
  tools: AgentToolCall[];
  handoffs: AgentHandoff[];
  validations: AgentOutputValidation[];
  usage: AgentRunUsage;
  cost: AgentRunCost;
  policy: Record<string, unknown>;
  input_summary: Record<string, unknown>;
  raw: Record<string, unknown>;
};

export type AgentRunRecordSummary = {
  request_id: string;
  user_id: string;
  entrypoint: "chat" | "workspace_brief";
  runtime_used?: string | null;
  model_name?: string | null;
  selected_agents: string[];
  tool_calls: AgentToolCall[];
  handoffs: AgentHandoff[];
  output_validations: AgentOutputValidation[];
  output_contract?: string | null;
  audit_status?: string | null;
  usage: AgentRunUsage;
  cost?: AgentRunCost;
  error_type?: string | null;
};

export type AgentRunFilters = {
  entrypoint?: "chat" | "workspace_brief" | "";
  hasError?: boolean | null;
  createdFrom?: string;
  createdTo?: string;
  offset?: number;
};

export type HarnessEvalResult = {
  case_id: string;
  passed: boolean;
  failures: string[];
};

export type ReplayRunReport = {
  request_id: string;
  record_found: boolean;
  case_id?: string | null;
  record_summary?: AgentRunRecordSummary | null;
  evaluation?: HarnessEvalResult | null;
  error?: string | null;
};

export type EvalCaseSummary = {
  case_id: string;
  entrypoint: "chat" | "workspace_brief";
  user_id: string;
  expected: {
    selected_agents: string[];
    required_tool_calls: string[];
    output_validations: AgentOutputValidation[];
    output_contract?: string | null;
    audit_status?: string | null;
  };
};
