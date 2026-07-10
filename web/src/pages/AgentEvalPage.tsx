import { useEffect, useState } from "react";
import { CheckCircle2, ClipboardCheck, XCircle } from "lucide-react";
import { fetchEvalCases } from "../services/supabaseApi";
import type { EvalCaseSummary } from "../types/agentRun";

export function AgentEvalPage() {
  const [cases, setCases] = useState<EvalCaseSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchEvalCases()
      .then((nextCases) => {
        if (!cancelled) setCases(nextCases);
      })
      .catch((caught: any) => {
        if (!cancelled) setError(caught?.message ?? "Failed to load eval cases");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-[#172026]">Agent Eval</h1>
          <p className="mt-2 text-sm text-[#697571]">
            Fixture-level expectations for selected agents, required tools,
            handoffs, output contracts, and audit status.
          </p>
        </div>
        <div className="rounded-2xl border border-[#dfe5e3] bg-white px-4 py-3 text-sm text-[#172026]">
          {loading ? "Loading" : `${cases.length} cases`}
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {cases.map((item) => (
          <article key={item.case_id} className="rounded-3xl border border-[#dfe5e3] bg-white p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold text-[#172026]">
                  <ClipboardCheck className="h-4 w-4 text-[#4b8078]" />
                  {item.case_id}
                </div>
                <div className="mt-1 text-xs text-[#697571]">
                  {item.entrypoint} · {item.user_id}
                </div>
              </div>
              <span className="rounded-full bg-[#ecfdf5] px-3 py-1 text-xs font-medium text-[#047857]">
                fixture
              </span>
            </div>
            <div className="mt-4 grid gap-3 text-sm">
              <EvalLine label="Agents" values={item.expected.selected_agents} />
              <EvalLine label="Tools" values={item.expected.required_tool_calls} />
              <EvalLine
                label="Contracts"
                values={item.expected.output_validations.map(
                  (validation) => `${validation.agent}.${validation.contract}:${validation.status}`
                )}
              />
              <div className="flex items-center gap-2 text-xs text-[#53615d]">
                {item.expected.audit_status ? (
                  <CheckCircle2 className="h-4 w-4 text-[#047857]" />
                ) : (
                  <XCircle className="h-4 w-4 text-[#9ca3af]" />
                )}
                Audit expectation: {item.expected.audit_status ?? "none"}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function EvalLine({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <div className="mb-2 text-xs uppercase tracking-[0.18em] text-[#8b9693]">{label}</div>
      <div className="flex flex-wrap gap-2">
        {values.length === 0 ? (
          <span className="rounded-full bg-[#f7f8f8] px-2.5 py-1 text-xs text-[#697571]">none</span>
        ) : (
          values.map((value) => (
            <span key={value} className="rounded-full bg-[#eef5f3] px-2.5 py-1 text-xs text-[#315f58]">
              {value}
            </span>
          ))
        )}
      </div>
    </div>
  );
}
