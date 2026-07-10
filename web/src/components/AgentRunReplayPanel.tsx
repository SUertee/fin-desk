import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { fetchAgentRuns, replayAgentRun } from "../services/supabaseApi";
import type {
  AgentHandoff,
  AgentRunPagination,
  AgentOutputValidation,
  AgentRunSummary,
  AgentToolCall,
  ReplayRunReport,
} from "../types/agentRun";

type AgentRunReplayPanelProps = {
  userId: string;
};

const EVAL_CASES = [
  { id: "", label: "Replay only" },
  { id: "chat_spending_review", label: "Chat: spending review" },
  { id: "chat_budget_plan", label: "Chat: budget plan" },
  { id: "analyze_cashflow_snapshot", label: "Analyze: cashflow snapshot" },
] as const;

const PAGE_SIZE = 10;

function shortId(value: string) {
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function formatDate(value?: string) {
  if (!value) return "No timestamp";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatNumber(value?: number | null) {
  return typeof value === "number" ? value.toLocaleString() : "0";
}

function formatCost(value?: number | null, currency = "USD") {
  if (typeof value !== "number") return `0 ${currency}`;
  return `${value.toFixed(value > 0 && value < 0.01 ? 6 : 4)} ${currency}`;
}

function statusStyle(status?: string | null) {
  if (status === "passed" || status === "called" || status === "completed") {
    return { background: "#ecfdf5", color: "#047857", borderColor: "#bbf7d0" };
  }
  if (status === "failed") {
    return { background: "#fef2f2", color: "#b91c1c", borderColor: "#fecaca" };
  }
  return { background: "#f8fafc", color: "#475569", borderColor: "#e2e8f0" };
}

function StatusPill({ status }: { status?: string | null }) {
  return (
    <span
      className="text-xs border rounded-full"
      style={{ padding: "2px 8px", ...statusStyle(status) }}
    >
      {status ?? "unknown"}
    </span>
  );
}

function EmptyState() {
  return (
    <div className="text-sm text-gray-500" style={{ padding: "18px 0" }}>
      No persisted agent runs yet. Send a chat message or run `/analyze` with
      Postgres enabled, then refresh this panel.
    </div>
  );
}

function RunListItem({
  run,
  selected,
  onSelect,
}: {
  run: AgentRunSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className="text-left border rounded-lg"
      style={{
        width: "100%",
        padding: "12px",
        background: selected ? "#0f172a" : "#ffffff",
        color: selected ? "#ffffff" : "#0f172a",
        borderColor: selected ? "#0f172a" : "#e5e7eb",
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm">{run.entrypoint}</span>
        <StatusPill status={run.error_type ? "failed" : run.runtime_used ?? "pending"} />
      </div>
      <div
        className="text-xs"
        style={{ marginTop: "6px", color: selected ? "#cbd5e1" : "#64748b" }}
      >
        {shortId(run.request_id)}
      </div>
      <div
        className="text-xs"
        style={{ marginTop: "6px", color: selected ? "#cbd5e1" : "#64748b" }}
      >
        {formatNumber(run.usage?.total_tokens)} tokens ·{" "}
        {formatCost(run.cost?.estimated_total_cost, run.cost?.currency)}
      </div>
    </button>
  );
}

function ToolRow({ tool }: { tool: AgentToolCall }) {
  return (
    <div
      className="border rounded-lg"
      style={{ padding: "10px", borderColor: "#e5e7eb" }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-slate-900">{tool.name}</span>
        <StatusPill status={tool.status} />
      </div>
      <div className="text-xs text-gray-500" style={{ marginTop: "4px" }}>
        {tool.agent ?? "agent unknown"}
        {typeof tool.latency_ms === "number" ? ` · ${tool.latency_ms}ms` : ""}
      </div>
    </div>
  );
}

function HandoffRow({ handoff }: { handoff: AgentHandoff }) {
  return (
    <div
      className="border rounded-lg"
      style={{ padding: "10px", borderColor: "#e5e7eb" }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-slate-900">
          {handoff.from_agent} → {handoff.to_agent}
        </span>
        <StatusPill status={handoff.status} />
      </div>
      <div className="text-xs text-gray-500" style={{ marginTop: "4px" }}>
        {handoff.reason ?? "no reason recorded"}
      </div>
    </div>
  );
}

function ValidationRow({
  validation,
}: {
  validation: AgentOutputValidation;
}) {
  return (
    <div
      className="border rounded-lg"
      style={{ padding: "10px", borderColor: "#e5e7eb" }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-slate-900">
          {validation.agent}.{validation.contract}
        </span>
        <StatusPill status={validation.status} />
      </div>
      {validation.errors.length > 0 && (
        <div className="text-xs text-red-600" style={{ marginTop: "6px" }}>
          {validation.errors.join(" · ")}
        </div>
      )}
    </div>
  );
}

export function AgentRunReplayPanel({ userId }: AgentRunReplayPanelProps) {
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [pagination, setPagination] = useState<AgentRunPagination>({
    limit: PAGE_SIZE,
    offset: 0,
    has_more: false,
    next_offset: null,
    previous_offset: null,
  });
  const [selectedRequestId, setSelectedRequestId] = useState("");
  const [caseId, setCaseId] = useState("");
  const [entrypointFilter, setEntrypointFilter] = useState<
    "" | "chat" | "analyze"
  >("");
  const [errorFilter, setErrorFilter] = useState<"all" | "error" | "success">("all");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [report, setReport] = useState<ReplayRunReport | null>(null);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isReplaying, setIsReplaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedRun = useMemo(
    () => runs.find((run) => run.request_id === selectedRequestId) ?? null,
    [runs, selectedRequestId]
  );

  const loadRuns = useCallback(async () => {
    setIsLoadingRuns(true);
    setError(null);
    try {
      const hasError =
        errorFilter === "all" ? null : errorFilter === "error";
      const nextPage = await fetchAgentRuns(userId, PAGE_SIZE, {
        entrypoint: entrypointFilter,
        hasError,
        createdFrom: createdFrom ? `${createdFrom}T00:00:00Z` : undefined,
        createdTo: createdTo ? `${createdTo}T23:59:59Z` : undefined,
        offset: pagination.offset,
      });
      const nextRuns = nextPage.runs;
      setRuns(nextRuns);
      setPagination(nextPage.pagination);
      setSelectedRequestId((current) => {
        if (current && nextRuns.some((run) => run.request_id === current)) {
          return current;
        }
        return nextRuns[0]?.request_id ?? "";
      });
    } catch (caught: any) {
      setError(caught?.message ?? "Failed to load agent runs");
    } finally {
      setIsLoadingRuns(false);
    }
  }, [createdFrom, createdTo, entrypointFilter, errorFilter, pagination.offset, userId]);

  const loadReplay = useCallback(async () => {
    if (!selectedRequestId) {
      setReport(null);
      return;
    }
    setIsReplaying(true);
    setError(null);
    try {
      const nextReport = await replayAgentRun(selectedRequestId, caseId || undefined);
      setReport(nextReport);
    } catch (caught: any) {
      setReport(null);
      setError(caught?.message ?? "Failed to replay agent run");
    } finally {
      setIsReplaying(false);
    }
  }, [caseId, selectedRequestId]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    void loadReplay();
  }, [loadReplay]);

  const summary = report?.record_summary ?? null;
  const evaluation = report?.evaluation ?? null;
  const validationFailures =
    summary?.output_validations.filter((item) => item.status === "failed") ?? [];

  return (
    <section className="bg-white rounded-lg border border-gray-200">
      <div className="px-5 py-4 border-b border-gray-200">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Workflow className="w-5 h-5 text-teal-600" />
              <h3 className="text-sm text-gray-900">Agent Harness Replay</h3>
            </div>
            <div className="text-xs text-gray-500" style={{ marginTop: "4px" }}>
              Persisted OpenAI Agents SDK run ledger, replay, and contract checks.
            </div>
          </div>
          <button
            type="button"
            onClick={loadRuns}
            className="border rounded-lg text-xs text-slate-700"
            style={{ padding: "8px 10px", borderColor: "#e5e7eb" }}
            disabled={isLoadingRuns}
          >
            <span className="flex items-center gap-2">
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh
            </span>
          </button>
        </div>
      </div>

      <div className="px-5 py-4">
        {error && (
          <div
            className="text-xs text-red-600 border rounded-lg"
            style={{ padding: "10px", marginBottom: "14px", borderColor: "#fecaca" }}
          >
            {error}
          </div>
        )}

        {runs.length === 0 && !isLoadingRuns ? (
          <EmptyState />
        ) : (
          <div
            className="grid gap-4"
            style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs text-gray-500">
                  Recent runs {isLoadingRuns ? "loading..." : `(${runs.length})`}
                </div>
              </div>
              <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <select
                  value={entrypointFilter}
                  onChange={(event) => {
                    setEntrypointFilter(event.target.value as "" | "chat" | "analyze");
                    setPagination((current) => ({ ...current, offset: 0 }));
                  }}
                  className="border rounded-lg text-xs text-slate-700 bg-white"
                  style={{ padding: "8px 10px", borderColor: "#e5e7eb" }}
                >
                  <option value="">All entrypoints</option>
                  <option value="chat">Chat</option>
                  <option value="analyze">Analyze</option>
                </select>
                <select
                  value={errorFilter}
                  onChange={(event) => {
                    setErrorFilter(event.target.value as "all" | "error" | "success");
                    setPagination((current) => ({ ...current, offset: 0 }));
                  }}
                  className="border rounded-lg text-xs text-slate-700 bg-white"
                  style={{ padding: "8px 10px", borderColor: "#e5e7eb" }}
                >
                  <option value="all">All outcomes</option>
                  <option value="success">Success only</option>
                  <option value="error">Errors only</option>
                </select>
              </div>
              <div className="grid gap-2" style={{ gridTemplateColumns: "1fr 1fr" }}>
                <input
                  type="date"
                  value={createdFrom}
                  onChange={(event) => {
                    setCreatedFrom(event.target.value);
                    setPagination((current) => ({ ...current, offset: 0 }));
                  }}
                  className="border rounded-lg text-xs text-slate-700 bg-white"
                  style={{ padding: "8px 10px", borderColor: "#e5e7eb" }}
                  aria-label="Created from"
                />
                <input
                  type="date"
                  value={createdTo}
                  onChange={(event) => {
                    setCreatedTo(event.target.value);
                    setPagination((current) => ({ ...current, offset: 0 }));
                  }}
                  className="border rounded-lg text-xs text-slate-700 bg-white"
                  style={{ padding: "8px 10px", borderColor: "#e5e7eb" }}
                  aria-label="Created to"
                />
              </div>
              {runs.map((run) => (
                <RunListItem
                  key={run.request_id}
                  run={run}
                  selected={run.request_id === selectedRequestId}
                  onSelect={() => setSelectedRequestId(run.request_id)}
                />
              ))}
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  className="border rounded-lg text-xs text-slate-700"
                  style={{ padding: "7px 10px", borderColor: "#e5e7eb" }}
                  disabled={pagination.previous_offset == null || isLoadingRuns}
                  onClick={() =>
                    setPagination((current) => ({
                      ...current,
                      offset: current.previous_offset ?? 0,
                    }))
                  }
                >
                  Previous
                </button>
                <div className="text-xs text-gray-500">
                  Offset {pagination.offset}
                </div>
                <button
                  type="button"
                  className="border rounded-lg text-xs text-slate-700"
                  style={{ padding: "7px 10px", borderColor: "#e5e7eb" }}
                  disabled={!pagination.has_more || isLoadingRuns}
                  onClick={() =>
                    setPagination((current) => ({
                      ...current,
                      offset: current.next_offset ?? current.offset,
                    }))
                  }
                >
                  Next
                </button>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-xs text-gray-500">Selected request</div>
                  <div className="text-sm text-slate-900">
                    {selectedRun ? shortId(selectedRun.request_id) : "No run selected"}
                  </div>
                </div>
                <select
                  value={caseId}
                  onChange={(event) => setCaseId(event.target.value)}
                  className="border rounded-lg text-xs text-slate-700 bg-white"
                  style={{ padding: "8px 10px", borderColor: "#e5e7eb" }}
                >
                  {EVAL_CASES.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>

              {isReplaying && (
                <div className="text-xs text-gray-500">Replaying run...</div>
              )}

              {summary && (
                <>
                  <div
                    className="grid gap-3"
                    style={{ gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))" }}
                  >
                    <div className="bg-slate-50 rounded-lg" style={{ padding: "12px" }}>
                      <div className="text-xs text-gray-500">Runtime</div>
                      <div className="text-sm text-slate-900">
                        {summary.runtime_used ?? "not completed"}
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg" style={{ padding: "12px" }}>
                      <div className="text-xs text-gray-500">Model</div>
                      <div className="text-sm text-slate-900">
                        {summary.model_name ?? "unknown"}
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg" style={{ padding: "12px" }}>
                      <div className="text-xs text-gray-500">Contract</div>
                      <div className="text-sm text-slate-900">
                        {summary.output_contract ?? "none"}
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg" style={{ padding: "12px" }}>
                      <div className="text-xs text-gray-500">Tokens</div>
                      <div className="text-sm text-slate-900">
                        {formatNumber(summary.usage.total_tokens)}
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg" style={{ padding: "12px" }}>
                      <div className="text-xs text-gray-500">Cost</div>
                      <div className="text-sm text-slate-900">
                        {formatCost(
                          summary.cost?.estimated_total_cost,
                          summary.cost?.currency
                        )}
                      </div>
                    </div>
                    <div className="bg-slate-50 rounded-lg" style={{ padding: "12px" }}>
                      <div className="text-xs text-gray-500">Audit</div>
                      <div className="text-sm text-slate-900">
                        {summary.audit_status ?? summary.error_type ?? "clean"}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                    {summary.selected_agents.map((agent) => (
                      <span
                        key={agent}
                        className="text-xs border rounded-full"
                        style={{
                          padding: "4px 9px",
                          borderColor: "#ccfbf1",
                          background: "#f0fdfa",
                          color: "#0f766e",
                        }}
                      >
                        {agent}
                      </span>
                    ))}
                  </div>

                  {evaluation && (
                    <div
                      className="border rounded-lg"
                      style={{
                        padding: "12px",
                        borderColor: evaluation.passed ? "#bbf7d0" : "#fecaca",
                        background: evaluation.passed ? "#f0fdf4" : "#fef2f2",
                      }}
                    >
                      <div className="flex items-center gap-2">
                        {evaluation.passed ? (
                          <CheckCircle2 className="w-4 h-4 text-green-600" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 text-red-600" />
                        )}
                        <span className="text-sm text-slate-900">
                          Eval {evaluation.case_id}:{" "}
                          {evaluation.passed ? "passed" : "failed"}
                        </span>
                      </div>
                      {evaluation.failures.length > 0 && (
                        <div className="text-xs text-red-600" style={{ marginTop: "8px" }}>
                          {evaluation.failures.join(" · ")}
                        </div>
                      )}
                    </div>
                  )}

                  {validationFailures.length > 0 && (
                    <div
                      className="border rounded-lg"
                      style={{ padding: "12px", borderColor: "#fecaca" }}
                    >
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-red-600" />
                        <span className="text-sm text-slate-900">
                          Output validation failures need review
                        </span>
                      </div>
                    </div>
                  )}

                  <div
                    className="grid gap-3"
                    style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}
                  >
                    <div>
                      <div className="flex items-center gap-2" style={{ marginBottom: "8px" }}>
                        <Workflow className="w-4 h-4 text-teal-600" />
                        <div className="text-xs text-gray-500">Tool calls</div>
                      </div>
                      <div className="space-y-2">
                        {summary.tool_calls.length > 0 ? (
                          summary.tool_calls.map((tool, index) => (
                            <ToolRow key={`${tool.name}-${index}`} tool={tool} />
                          ))
                        ) : (
                          <div className="text-xs text-gray-500">No tool calls.</div>
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center gap-2" style={{ marginBottom: "8px" }}>
                        <GitBranch className="w-4 h-4 text-teal-600" />
                        <div className="text-xs text-gray-500">Handoffs</div>
                      </div>
                      <div className="space-y-2">
                        {summary.handoffs.length > 0 ? (
                          summary.handoffs.map((handoff, index) => (
                            <HandoffRow
                              key={`${handoff.from_agent}-${handoff.to_agent}-${index}`}
                              handoff={handoff}
                            />
                          ))
                        ) : (
                          <div className="text-xs text-gray-500">No handoffs.</div>
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center gap-2" style={{ marginBottom: "8px" }}>
                        <ShieldCheck className="w-4 h-4 text-teal-600" />
                        <div className="text-xs text-gray-500">Output validations</div>
                      </div>
                      <div className="space-y-2">
                        {summary.output_validations.length > 0 ? (
                          summary.output_validations.map((validation, index) => (
                            <ValidationRow
                              key={`${validation.agent}-${validation.contract}-${index}`}
                              validation={validation}
                            />
                          ))
                        ) : (
                          <div className="text-xs text-gray-500">
                            No validations recorded.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="text-xs text-gray-500">
                    Created {formatDate(selectedRun?.created_at)} · request{" "}
                    {summary.request_id}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
