import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Braces, CheckCircle2, RefreshCw, Workflow } from "lucide-react";
import {
  fetchAgentRunProjection,
  fetchAgentRuns,
} from "../services/financeApi";
import type {
  AgentRunProjection,
  AgentRunSummary,
  AgentRunTimelineItem,
} from "../types/agentRun";

type AgentObservabilityPageProps = {
  userId: string;
};

export function AgentObservabilityPage({ userId }: AgentObservabilityPageProps) {
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState("");
  const [projection, setProjection] = useState<AgentRunProjection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingProjection, setLoadingProjection] = useState(false);

  const selectedRun = useMemo(
    () => runs.find((run) => run.request_id === selectedRequestId) ?? null,
    [runs, selectedRequestId]
  );

  const loadRuns = useCallback(async () => {
    setLoadingRuns(true);
    setError(null);
    try {
      const payload = await fetchAgentRuns(userId, 12);
      setRuns(payload.runs);
      setSelectedRequestId((current) => {
        if (current && payload.runs.some((run) => run.request_id === current)) {
          return current;
        }
        return payload.runs[0]?.request_id ?? "";
      });
    } catch (caught: any) {
      setError(caught?.message ?? "Failed to load agent runs");
    } finally {
      setLoadingRuns(false);
    }
  }, [userId]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (!selectedRequestId) {
      setProjection(null);
      return;
    }
    let cancelled = false;
    setLoadingProjection(true);
    fetchAgentRunProjection(selectedRequestId)
      .then((nextProjection) => {
        if (!cancelled) setProjection(nextProjection);
      })
      .catch((caught: any) => {
        if (!cancelled) {
          setProjection(null);
          setError(caught?.message ?? "Failed to load projected run");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingProjection(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRequestId]);

  return (
    <section className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#172026]">Agent Observability</h1>
          <p className="mt-2 text-sm text-[#697571]">
            Inspect the self-hosted runtime trace: selected agents, tool calls,
            typed handoffs, validations, usage, cost, and raw record.
          </p>
        </div>
        <button
          type="button"
          onClick={loadRuns}
          disabled={loadingRuns}
          className="inline-flex items-center gap-2 rounded-2xl border border-[#dfe5e3] bg-white px-4 py-2 text-sm text-[#172026]"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
        <div className="rounded-3xl border border-[#dfe5e3] bg-white p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#172026]">
            <Workflow className="h-4 w-4 text-[#4b8078]" />
            Recent Runs
          </div>
          {runs.length === 0 ? (
            <div className="rounded-2xl bg-[#f7f8f8] p-4 text-sm text-[#697571]">
              {loadingRuns ? "Loading runs..." : "No persisted runs yet."}
            </div>
          ) : (
            <div className="space-y-2">
              {runs.map((run) => (
                <button
                  key={run.request_id}
                  type="button"
                  onClick={() => setSelectedRequestId(run.request_id)}
                  className={`w-full rounded-2xl border p-3 text-left transition ${
                    selectedRequestId === run.request_id
                      ? "border-[#172026] bg-[#172026] text-white"
                      : "border-[#dfe5e3] bg-white text-[#172026] hover:bg-[#f7f8f8]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span>{run.entrypoint}</span>
                    <span>{run.error_type ? "failed" : run.runtime_used ?? "pending"}</span>
                  </div>
                  <div className="mt-1 truncate text-sm font-medium">{run.request_id}</div>
                  <div className="mt-1 text-xs opacity-70">
                    {run.usage?.total_tokens ?? 0} tokens · {run.audit_status ?? "no audit"}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-5">
          {selectedRun && (
            <div className="rounded-3xl border border-[#dfe5e3] bg-white p-5">
              <div className="grid gap-3 md:grid-cols-4">
                <Metric label="Runtime" value={projection?.summary.runtime_used ?? selectedRun.runtime_used ?? "pending"} />
                <Metric label="Agents" value={String(projection?.summary.selected_agents.length ?? 0)} />
                <Metric label="Audit" value={projection?.summary.audit_status ?? "none"} />
                <Metric label="Latency" value={`${projection?.summary.latency_ms ?? 0}ms`} />
              </div>
            </div>
          )}

          <div className="rounded-3xl border border-[#dfe5e3] bg-white p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[#172026]">Timeline</h2>
              {loadingProjection && <span className="text-xs text-[#697571]">Loading...</span>}
            </div>
            {projection ? (
              <div className="grid gap-3">
                {projection.timeline.map((item, index) => (
                  <TimelineItem key={`${item.kind}-${item.label}-${index}`} item={item} />
                ))}
              </div>
            ) : (
              <div className="text-sm text-[#697571]">Select a run to inspect.</div>
            )}
          </div>

          {projection && (
            <div className="grid gap-5 xl:grid-cols-2">
              <Section title="Tools" items={projection.tools.map((tool) => `${tool.name}: ${tool.status}`)} />
              <Section
                title="Handoffs"
                items={projection.handoffs.map(
                  (handoff) => `${handoff.from_agent} -> ${handoff.to_agent}: ${handoff.status}`
                )}
              />
              <Section
                title="Validations"
                items={projection.validations.map(
                  (validation) => `${validation.agent}.${validation.contract}: ${validation.status}`
                )}
              />
              <div className="rounded-3xl border border-[#dfe5e3] bg-white p-5">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-[#172026]">
                  <Braces className="h-4 w-4 text-[#4b8078]" />
                  Raw JSON
                </div>
                <pre className="max-h-80 overflow-auto rounded-2xl bg-[#101918] p-4 text-xs leading-5 text-[#d8e7e3]">
                  {JSON.stringify(projection.raw, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-[#f7f8f8] p-4">
      <div className="text-xs uppercase tracking-[0.18em] text-[#8b9693]">{label}</div>
      <div className="mt-1 truncate text-sm font-semibold text-[#172026]">{value}</div>
    </div>
  );
}

function TimelineItem({ item }: { item: AgentRunTimelineItem }) {
  const failed = item.status === "failed";
  const Icon = failed ? AlertTriangle : CheckCircle2;
  return (
    <div className="flex gap-3 rounded-2xl border border-[#dfe5e3] bg-[#f9fbfa] p-3">
      <div className={`mt-0.5 ${failed ? "text-red-600" : "text-[#4b8078]"}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-3">
          <div className="truncate text-sm font-medium text-[#172026]">{item.label}</div>
          <div className="rounded-full bg-white px-2 py-0.5 text-xs text-[#697571]">
            {item.kind}
          </div>
        </div>
        <div className="mt-1 text-xs text-[#697571]">
          {item.status ?? "unknown"}
          {item.agent ? ` · ${item.agent}` : ""}
          {item.reason ? ` · ${item.reason}` : ""}
          {typeof item.latency_ms === "number" ? ` · ${item.latency_ms}ms` : ""}
        </div>
      </div>
    </div>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-3xl border border-[#dfe5e3] bg-white p-5">
      <h2 className="mb-3 text-sm font-semibold text-[#172026]">{title}</h2>
      <div className="space-y-2">
        {items.length === 0 ? (
          <div className="text-sm text-[#697571]">No records.</div>
        ) : (
          items.map((item) => (
            <div key={item} className="rounded-2xl bg-[#f7f8f8] px-3 py-2 text-sm text-[#53615d]">
              {item}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
