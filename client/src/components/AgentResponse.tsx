import {
  AlertTriangle,
  BadgeCheck,
  CheckCircle2,
  CircleDot,
} from "lucide-react";
import type { FinanceAgentData } from "../types/financeAgent";

type AgentResponseProps = {
  content: string;
  data?: FinanceAgentData | null;
};

const auditLabel = {
  verified: "Verified",
  needs_review: "Needs review",
  data_limited: "Data limited",
};

export function AgentResponse({ content, data }: AgentResponseProps) {
  const audit = data?.audit ?? null;

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
                <div className="font-medium text-[#24302c]">{finding.title}</div>
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
          <span>{Math.round(audit.confidence * 100)}% confidence</span>
        </div>
      )}
    </div>
  );
}
