import type { AnalysisRunRow, TransactionRow } from "../types/db";
import type { ChatResponse } from "../types/financeAgent";
import type {
  AgentRunFilters,
  AgentRunListResponse,
  AgentRunProjection,
  AgentRunSummary,
  EvalCaseSummary,
  ReplayRunReport,
} from "../types/agentRun";

const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:18000";

export function getApiBaseUrl() {
  return apiBaseUrl;
}

export type StatementImportRecord = {
  import_id: string;
  user_id: string;
  source_file: string;
  source_format: string;
  imported_count: number;
  status: "succeeded" | "failed" | string;
  error: string;
  sample: Record<string, unknown>[];
  created_at: string | null;
};

export type DataSourceChannel = {
  id: string;
  label: string;
  status: string;
  mode: string;
  recommended: boolean;
};

export type DataSourceStatus = {
  ok: boolean;
  user_id: string;
  transaction_count: number;
  latest_import: StatementImportRecord | null;
  import_history: StatementImportRecord[];
  channels: DataSourceChannel[];
};

export interface DailyTotal {
  date: string;
  expense: number;
  income: number;
  count: number;
}

export interface DailyTotalsResponse {
  user_id: string;
  month: string;
  days: DailyTotal[];
  totals: { expense: number; income: number; count: number };
}

export async function fetchDailyTotals(
  userId: string,
  month: string
): Promise<DailyTotalsResponse> {
  const response = await fetch(
    `${apiBaseUrl}/transactions/daily/${encodeURIComponent(userId)}?month=${month}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as DailyTotalsResponse;
}

export async function fetchTransactionsForDay(userId: string, day: string) {
  const response = await fetch(
    `${apiBaseUrl}/transactions/${encodeURIComponent(userId)}?date_from=${day}&date_to=${day}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { items: any[] };
}

export async function fetchTransactions(userId: string, limit = 200) {
  const response = await fetch(
    `${apiBaseUrl}/transactions/${encodeURIComponent(userId)}?limit=${limit}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  return (payload.items ?? []) as TransactionRow[];
}

export async function fetchProfile(userId: string) {
  const response = await fetch(
    `${apiBaseUrl}/profile/${encodeURIComponent(userId)}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as { monthly_income: number; monthly_expenses: number; name: string; [key: string]: any };
}

export type ProfileUpdatePayload = {
  name?: string;
  occupation?: string;
  financial_goals?: string[];
  risk_tolerance?: string;
  cash_balance?: number;
  savings?: number;
  investments?: number;
  liabilities?: number;
  monthly_income?: number;
  monthly_expenses?: number;
  notes?: string;
  preferences?: UserPreferencesPayload;
};

export type UserPreferencesPayload = {
  response_tone: "concise" | "balanced" | "comprehensive";
  preferred_language: "en" | "zh" | "auto";
  evidence_level: "brief" | "detailed" | "audit_heavy";
};

export async function updateProfile(
  userId: string,
  payload: ProfileUpdatePayload
) {
  const response = await fetch(
    `${apiBaseUrl}/profile/${encodeURIComponent(userId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.error ?? "Failed to update profile");
  }
  return body as {
    user_id: string;
    name: string;
    occupation: string;
    financial_goals: string[];
    risk_tolerance: string;
    assets: {
      cash_balance: number;
      savings: number;
      investments: number;
      liabilities: number;
      net_worth?: number;
    };
    monthly_income: number;
    monthly_expenses: number;
    notes: string;
  };
}

export async function fetchLatestAnalysisRun(userId: string) {
  const response = await fetch(
    `${apiBaseUrl}/analysis-runs/latest/${encodeURIComponent(userId)}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  return payload as AnalysisRunRow | null;
}

export async function fetchDataSourceStatus(
  userId: string
): Promise<DataSourceStatus> {
  const response = await fetch(
    `${apiBaseUrl}/data-sources/status/${encodeURIComponent(userId)}`
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Failed to load data-source status");
  }
  return payload as DataSourceStatus;
}

export async function importStatement(userId: string, file: File) {
  const formData = new FormData();
  formData.append("user_id", userId);
  formData.append("file", file);

  const response = await fetch(`${apiBaseUrl}/statement-import/import`, {
    method: "POST",
    body: formData,
  });
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload?.error ?? "Statement import failed");
  }

  return payload as StatementImportResult;
}

export interface StatementImportResult {
  ok: boolean;
  user_id: string;
  source_file: string;
  imported_count: number;
  detected_source?: string;
  already_imported_count?: number;
  duplicates?: Array<{
    date: string;
    description: string;
    amount: number;
    source: string;
    duplicate_of: string;
    duplicate_of_source: string;
    reason: string;
  }>;
  parse_report?: {
    detected_source: string;
    encoding_or_format: string;
    total_rows: number;
    parsed_rows: number;
    skipped: Array<{ line_no: number; reason_code: string; snippet: string }>;
  };
}

export async function sendChatMessage(
  userId: string,
  message: string,
  requestedSpecialist?: string
): Promise<ChatResponse> {
  const response = await fetch(`${apiBaseUrl}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
      requested_specialist: requestedSpecialist ?? null,
    }),
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return (await response.json()) as ChatResponse;
}

export async function fetchAgentRuns(
  userId: string,
  limit = 10,
  filters: AgentRunFilters = {}
): Promise<AgentRunListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters.offset) params.set("offset", String(filters.offset));
  if (filters.entrypoint) params.set("entrypoint", filters.entrypoint);
  if (filters.hasError !== null && filters.hasError !== undefined) {
    params.set("has_error", String(filters.hasError));
  }
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);

  const response = await fetch(
    `${apiBaseUrl}/agent-runs/user/${encodeURIComponent(userId)}?${params.toString()}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  return {
    runs: (payload.runs ?? []) as AgentRunSummary[],
    pagination: payload.pagination ?? {
      limit,
      offset: filters.offset ?? 0,
      has_more: false,
      next_offset: null,
      previous_offset: null,
    },
  };
}

export async function replayAgentRun(requestId: string, caseId?: string) {
  const params = new URLSearchParams();
  if (caseId) params.set("case_id", caseId);

  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(
    `${apiBaseUrl}/agent-runs/${encodeURIComponent(requestId)}/replay${suffix}`
  );
  const payload = await response.json();

  if (!response.ok) {
    const error = payload?.error ?? "Agent run replay failed";
    throw new Error(error);
  }

  return payload.replay as ReplayRunReport;
}

export async function fetchAgentRunProjection(
  requestId: string
): Promise<AgentRunProjection> {
  const response = await fetch(
    `${apiBaseUrl}/agent-runs/${encodeURIComponent(requestId)}/projected`
  );
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Failed to load projected agent run");
  }
  return payload.projection as AgentRunProjection;
}

export async function fetchEvalCases(): Promise<EvalCaseSummary[]> {
  const response = await fetch(`${apiBaseUrl}/evals/cases`);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.error ?? "Failed to load eval cases");
  }
  return (payload.cases ?? []) as EvalCaseSummary[];
}

export async function fetchWorkspaceBrief(userId: string) {
  const response = await fetch(
    `${apiBaseUrl}/workspace/brief/${encodeURIComponent(userId)}`
  );
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as import("../types/financeAgent").WorkspaceBrief;
}

export type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "done"; response: ChatResponse }
  | { type: "error"; error: string };

export async function sendChatMessageStream(
  userId: string,
  message: string,
  requestedSpecialist: string | undefined,
  onEvent: (event: ChatStreamEvent) => void
): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      message,
      requested_specialist: requestedSpecialist ?? null,
    }),
  });
  if (!response.ok || !response.body) {
    throw new Error(await response.text());
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as ChatStreamEvent);
      } catch {
        // skip malformed frame
      }
    }
  }
}
