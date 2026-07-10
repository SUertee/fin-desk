export type AgentRunUsage = {
  request_count: number;
  model_response_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

export type AgentRunCost = {
  model_name?: string | null;
  currency: string;
  input_cost_per_1m?: number | null;
  output_cost_per_1m?: number | null;
  estimated_input_cost?: number;
  estimated_output_cost?: number;
  estimated_total_cost: number;
  pricing_source?: string;
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
  entrypoint: "chat" | "analyze";
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
    entrypoint: "chat" | "analyze";
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
  entrypoint: "chat" | "analyze";
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
  entrypoint?: "chat" | "analyze" | "";
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
  entrypoint: "chat" | "analyze";
  user_id: string;
  expected: {
    selected_agents: string[];
    required_tool_calls: string[];
    output_validations: AgentOutputValidation[];
    output_contract?: string | null;
    audit_status?: string | null;
  };
};
