import React, { useState } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  CircleDot,
  ScrollText,
} from "lucide-react";
import type { FinanceAgentData } from "../types/financeAgent";
import { fetchAgentRunProjection } from "../services/supabaseApi";

type AgentResponseProps = {
  content: string;
  data?: FinanceAgentData | null;
  requestId?: string | null;
};

const auditLabel = {
  verified: "Verified",
  needs_review: "Needs review",
  data_limited: "Data limited",
};

const AGENT_BADGE_COLORS: Record<string, string> = {
  cfo: "#172026",
  expense_analyst: "#4b8078",
  budget_coach: "#6f7f62",
  auditor: "#5f6f78",
  market_context: "#7b6f58",
};

function agentBadgeStyle(agent: string): React.CSSProperties {
  return {
    background: AGENT_BADGE_COLORS[agent] ?? "#75827e",
    color: "#ffffff",
    borderRadius: 5,
    padding: "1px 7px",
    fontSize: 10,
    fontWeight: 600,
    lineHeight: "16px",
    whiteSpace: "nowrap",
  };
}

type TraceSummary = {
  selectedAgents: string[];
  toolCalls: number;
  auditStatus: string | null;
  latencyMs: number | null;
};

export function AgentResponse({ content, data, requestId }: AgentResponseProps) {
  const audit = data?.audit ?? null;
  const [trace, setTrace] = useState<TraceSummary | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);

  const handleViewTrace = async () => {
    if (traceOpen) {
      setTraceOpen(false);
      return;
    }
    setTraceOpen(true);
    if (trace || !requestId) return;
    try {
      const projection: any = await fetchAgentRunProjection(requestId);
      const record = projection?.record ?? projection ?? {};
      setTrace({
        selectedAgents: record.selected_agents ?? [],
        toolCalls: (record.tool_calls ?? []).length,
        auditStatus: record.audit_status ?? null,
        latencyMs: record.latency_ms ?? null,
      });
    } catch (error: any) {
      setTraceError(error?.message ?? "Failed to load trace");
    }
  };

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-[#dfe5e3] bg-white px-3 py-3 text-sm leading-relaxed text-[#24302c]">
        {content}
      </div>

      {data?.findings && data.findings.length > 0 && (
        <section className="rounded-xl border border-[#dfe5e3] bg-[#f8faf9] p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[#172026]">
            <CircleDot className="h-3.5 w-3.5 text-[#4b8078]" />
            Findings
          </div>
          <div className="space-y-2">
            {data.findings.map((finding, index) => (
              <div key={`${finding.agent}-${index}`} className="text-xs text-[#53615d]">
                <div className="flex items-center gap-2">
                  <span style={agentBadgeStyle(finding.agent)}>{finding.agent}</span>
                  <span className="font-medium text-[#24302c]">{finding.title}</span>
                </div>
                {finding.evidence.length > 0 && (
                  <ul className="mt-1 space-y-1">
                    {finding.evidence.map((item, evidenceIndex) => (
                      <li key={evidenceIndex}>- {item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {data?.actions && data.actions.length > 0 && (
        <section className="rounded-xl border border-[#dfe5e3] bg-white p-3">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-[#172026]">
            <CheckCircle2 className="h-3.5 w-3.5 text-[#4b8078]" />
            Actions
          </div>
          <div className="space-y-2">
            {data.actions.map((action, index) => (
              <div key={`${action.title}-${index}`} className="text-xs">
                <div className="font-medium text-[#24302c]">{action.title}</div>
                <div className="mt-0.5 text-[#53615d]">{action.rationale}</div>
                <div className="mt-1 text-[11px] text-[#75827e]">
                  Effort {action.effort} · Impact {action.impact}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {audit && (
        <div className="flex items-center justify-between rounded-xl border border-[#dfe5e3] bg-[#f8faf9] px-3 py-2 text-xs text-[#53615d]">
          <div className="flex items-center gap-2">
            {audit.status === "verified" ? (
              <BadgeCheck className="h-3.5 w-3.5 text-[#4b8078]" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5 text-[#947348]" />
            )}
            <span>{auditLabel[audit.status]}</span>
          </div>
          <div className="flex items-center gap-3">
            <span>{Math.round(audit.confidence * 100)}% confidence</span>
            {requestId && (
              <button
                type="button"
                onClick={handleViewTrace}
                className="flex items-center gap-1 text-[#4b8078] underline-offset-2 hover:underline"
              >
                <ScrollText className="h-3 w-3" />
                {traceOpen ? "Hide trace" : "View trace"}
              </button>
            )}
          </div>
        </div>
      )}

      {traceOpen && requestId && (
        <div className="rounded-xl border border-dashed border-[#c9d4d1] bg-white px-3 py-2 text-[11px] text-[#53615d]">
          {traceError ? (
            <span>{traceError}</span>
          ) : trace ? (
            <div className="space-y-1">
              <div>Run: {requestId}</div>
              <div>Agents: {trace.selectedAgents.join(", ") || "—"}</div>
              <div>
                Tool calls: {trace.toolCalls}
                {trace.auditStatus ? ` · Audit: ${trace.auditStatus}` : ""}
                {trace.latencyMs != null ? ` · ${Math.round(trace.latencyMs)}ms` : ""}
              </div>
            </div>
          ) : (
            <span>Loading trace…</span>
          )}
        </div>
      )}
    </div>
  );
}
