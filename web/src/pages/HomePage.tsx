import { ArrowRight, Database, GitBranch, ShieldCheck, Workflow } from "lucide-react";
import type { PageId } from "./pageTypes";

type HomePageProps = {
  onNavigate: (page: PageId) => void;
  transactionCount: number;
  runCount: number;
};

const tiles: Array<{
  page: PageId;
  title: string;
  body: string;
}> = [
  {
    page: "workspace",
    title: "Finance Workspace",
    body: "User-facing CFO chat, transaction review, cash-flow summaries, and recommendations.",
  },
  {
    page: "observability",
    title: "Agent Observability",
    body: "Inspect selected agents, tool calls, typed handoffs, validations, usage, and raw traces.",
  },
  {
    page: "eval",
    title: "Agent Eval",
    body: "Review fixture expectations and use replay to catch regressions in orchestration behavior.",
  },
  {
    page: "settings",
    title: "Runtime Settings",
    body: "Verify API base URL, self-hosted runtime mode, persistence, and model profile boundaries.",
  },
];

export function HomePage({ onNavigate, transactionCount, runCount }: HomePageProps) {
  return (
    <section className="space-y-6">
      <div className="overflow-hidden rounded-[28px] border border-[#dfe5e3] bg-[#14201d] text-white shadow-[0_24px_70px_rgba(23,32,38,0.16)]">
        <div className="grid gap-8 px-8 py-8 lg:grid-cols-[1.4fr_0.8fr]">
          <div>
            <div className="mb-4 inline-flex rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs text-[#c8d8d3]">
              Self-hosted CFO-first multi-agent harness
            </div>
            <h1 className="max-w-3xl text-4xl font-semibold leading-tight tracking-[-0.04em]">
              Personal finance agent platform with typed A2A, run ledger, and eval replay.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-[#c8d8d3]">
              The backend owns orchestration: CFO planning, bounded tools,
              specialist handoffs, auditor review, trace projection, and
              regression evals. LLM providers stay behind `runtime/llm`.
            </p>
            <button
              type="button"
              onClick={() => onNavigate("workspace")}
              className="mt-6 inline-flex items-center gap-2 rounded-2xl bg-[#dce9a7] px-5 py-3 text-sm font-semibold text-[#172026]"
            >
              Open Finance Workspace
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
          <div className="grid gap-3">
            {[
              ["Loaded transactions", transactionCount.toLocaleString(), Database],
              ["Recent run rows", runCount.toLocaleString(), Workflow],
              ["Runtime mode", "self_hosted", GitBranch],
              ["Audit policy", "typed + persisted", ShieldCheck],
            ].map(([label, value, Icon]) => (
              <div key={label as string} className="rounded-2xl border border-white/10 bg-white/8 p-4">
                <Icon className="mb-3 h-5 w-5 text-[#dce9a7]" />
                <div className="text-xs uppercase tracking-[0.2em] text-[#91a39e]">{label}</div>
                <div className="mt-1 text-xl font-semibold">{value}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {tiles.map((tile) => (
          <button
            key={tile.page}
            type="button"
            onClick={() => onNavigate(tile.page)}
            className="group rounded-3xl border border-[#dfe5e3] bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="text-sm font-semibold text-[#172026]">{tile.title}</div>
            <div className="mt-2 text-sm leading-6 text-[#697571]">{tile.body}</div>
            <div className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-[#4b8078]">
              Open section
              <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-1" />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
