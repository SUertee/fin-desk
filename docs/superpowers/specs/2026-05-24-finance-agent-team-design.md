# Personal Finance Agent Team Design

Date: 2026-05-24

## Goal

Build a personal finance agent team that helps the user understand their current financial situation, identify risks and anomalies, and turn analysis into concrete actions. The system should feel like a calm finance operating system: professional, unified, restrained, and easy to scan.

The first implementation phase should prioritize an end-to-end experience:

- A unified CFO entry point that coordinates specialist agents.
- Specialist agents focused on monthly financial health, expense analysis, budgeting, behavior coaching, and audit review.
- A redesigned dashboard and agent panel using the selected "Calm Operating System" visual direction.
- A gradual migration to LangChain DeepAgents without breaking the existing FastAPI, database, or React app flow.

## Current Project Context

The repository is already structured as a full-stack finance assistant:

- `client/`: React + Vite dashboard with transaction views, charts, upload flow, and an AI sidebar.
- `server/`: FastAPI backend with database repositories, finance services, and a LangGraph-based multi-agent flow.
- `server/agents/graph.py`: current LangGraph router dispatches to specialist modules.
- `server/api/chat.py`: loads transactions, latest analysis run, and invokes the orchestrator.
- `server/services/llm.py`: supports Ollama and OpenAI-compatible providers.

The current architecture is a good base. The design should evolve it rather than replace it wholesale.

## Confirmed Direction

### Product Priority

Use an end-to-end plan: backend DeepAgents architecture and frontend agent team experience should be designed together, then implemented in stages.

### Runtime Strategy

Use a "start embedded, later extract" approach:

1. First embed the DeepAgents runtime inside the existing FastAPI service.
2. Preserve the current `/chat` route, database access, and React client integration.
3. Keep the current LangGraph orchestration as a fallback during migration.
4. Once the DeepAgents runtime stabilizes, consider extracting it into a separate agent runtime service.

### First Agent Team Scope

Expose one unified entry point and create a clear team model:

- `CFO`: primary user-facing agent and coordinator.
- `Expense Analyst`: spending categories, monthly deltas, anomalies, merchant concentration, duplicates.
- `Budget Coach`: budget limits, behavior patterns, low-friction interventions, reminders, substitution ideas.
- `Auditor`: factual checks, confidence, data limitations, risk labels, actionability review.
- `Market Scout`: lightweight financial news and market context, with conservative risk handling.

The first phase should emphasize monthly financial health and budget/behavior advice. Investment and market suggestions should remain lightweight and explicitly risk-aware.

## Backend Design

### Target Shape

Keep the public chat flow stable:

```text
POST /chat
  -> load user profile
  -> load transactions and latest analysis run
  -> load recent chat history
  -> invoke FinanceTeamRuntime
  -> return ChatResponse
```

Add a runtime boundary:

```text
server/agents/deep_runtime.py
  FinanceTeamRuntime
    - builds or loads CFO DeepAgent
    - passes finance context into the run
    - normalizes agent output
    - falls back to existing LangGraph orchestrator if needed
```

The CFO DeepAgent should be created with LangChain DeepAgents and configured with finance-specific tools and subagents. DeepAgents is appropriate here because its core capabilities are planning, subagent delegation, filesystem/context management, memory-oriented middleware, and long-running task support. It remains built on LangChain/LangGraph concepts, so it can fit the existing backend incrementally.

Primary official references:

- https://docs.langchain.com/oss/python/deepagents/subagents
- https://docs.langchain.com/oss/python/deepagents/customization
- https://reference.langchain.com/python/deepagents/graph/create_deep_agent

### Agent Responsibilities

`CFO`

- Owns the user-facing answer.
- Plans the analysis.
- Decides which specialist subagents are needed.
- Produces the final response in the user's language.
- Turns specialist findings into prioritized decisions.

`Expense Analyst`

- Computes spending summaries and category changes.
- Identifies anomalies and duplicate-sensitive totals.
- Explains whether changes look structural or one-off.
- Produces evidence snippets for the CFO.

`Budget Coach`

- Compares spending against income and goals.
- Suggests practical budget limits and behavior interventions.
- Keeps advice low-friction and specific.
- Avoids vague motivational guidance.

`Auditor`

- Reviews the final answer or specialist outputs.
- Flags weak evidence, missing data, risky claims, and overconfident investment advice.
- Adds confidence and warning metadata.

`Market Scout`

- Provides lightweight macro/news context only when relevant.
- Avoids acting as a standalone investment advisor.
- Always returns limitations and risk notes.

### Tools

Initial tools should be deterministic wrappers around current backend capabilities:

- `get_user_profile(user_id)`
- `get_recent_transactions(user_id, limit)`
- `get_monthly_totals(user_id)`
- `summarize_categories(transactions)`
- `detect_anomalies(transactions, monthly_totals)`
- `compare_budget(profile, transactions, monthly_totals)`
- `get_news_context(profile, query)` when configured

Do not let agents query the database directly. Tools should expose bounded, typed inputs and outputs.

### Output Contract

Continue returning the existing `ChatResponse`, but enrich `data` so the frontend can render structured insights:

```ts
type FinanceAgentData = {
  summary_cards?: Array<{
    label: string;
    value: string;
    status?: "neutral" | "good" | "watch" | "risk";
    note?: string;
  }>;
  findings?: Array<{
    agent: string;
    title: string;
    evidence: string[];
  }>;
  actions?: Array<{
    title: string;
    rationale: string;
    effort: "low" | "medium" | "high";
    impact: "low" | "medium" | "high";
  }>;
  audit?: {
    confidence: number;
    status: "verified" | "needs_review" | "data_limited";
    warnings: string[];
  };
};
```

The natural-language `reply` remains the primary answer. Structured data is additive and used for product UI.

### Error Handling

- If DeepAgents initialization fails, fall back to the current LangGraph graph and return a normal chat response.
- If a specialist tool fails, the CFO should continue with available evidence and the Auditor should label the answer `data_limited`.
- If the model returns malformed structured output, preserve the text reply and omit invalid structured sections.
- Never silently produce financial recommendations that look more certain than the underlying data supports.

### Migration Steps

1. Add the `deepagents` dependency and verify import/version compatibility.
2. Add typed finance tools around existing services and repositories.
3. Add `FinanceTeamRuntime` behind the current `/chat` route.
4. Implement CFO DeepAgent and subagent specs.
5. Add structured output normalization.
6. Add feature flag support, for example `FINANCE_AGENT_RUNTIME=deepagents|langgraph`.
7. Keep LangGraph fallback until the new runtime has enough coverage.

## Frontend Design

### Visual Direction

Use the selected "Calm Operating System" direction:

- Professional finance workspace, not a landing page.
- Light neutral background with white panels.
- Low-saturation teal/green accent color.
- Thin borders, subtle elevation, and stable spacing.
- Rounded corners should feel soft but not playful.
- Avoid emojis, loud gradients, bokeh/orb decorations, and sharp card edges.
- Text hierarchy should be compact and readable.

### Page Structure

Keep the application as a dashboard-first experience.

Top navigation:

- Product name.
- Data date range.
- Upload statement action.
- AI Team toggle.
- User/profile entry.

Main layout:

1. `Operating Summary`
   - Cash flow, income, spending, net position, budget risk, anomaly count, audit status.
   - Consolidates current `MetricsCards` and `IncomeSummary` into a more coherent summary area.

2. `Analysis Workspace`
   - Monthly trend chart.
   - Category breakdown.
   - Source breakdown.
   - Category comparison.
   - Transactions table.
   - Components should share spacing, borders, title treatment, and chart palette.

3. `Agent Team Panel`
   - Replaces the current plain AI sidebar.
   - Default view is `CFO`.
   - Shows specialist agents, status, responsibilities, and last contribution.
   - Includes chat, but also renders structured conclusions, evidence, actions, and audit labels.

### Agent Panel Behavior

- CFO is the default interaction mode.
- User can switch to a specialist agent, but does not have to.
- Agent replies should render as:
  - main answer,
  - key findings,
  - evidence,
  - action list,
  - audit status.
- Auditor status should use restrained labels such as `Verified`, `Needs review`, and `Data limited`.
- Mobile should treat the agent panel as a drawer. The dashboard summary and CFO entry point remain primary.

### Component Direction

Likely component changes:

- `DashboardShell`: owns layout, header spacing, and responsive panel behavior.
- `OperatingSummary`: unified summary cards and risk status.
- `AgentTeamPanel`: redesigned replacement for `AiSidebar`.
- `AgentRoster`: specialist cards and active agent selection.
- `AgentResponse`: structured rendering of reply, evidence, actions, and audit metadata.
- Existing chart/table components should be restyled before being deeply rewritten.

## Testing And Verification

Backend:

- Unit tests for finance tools using deterministic sample transactions.
- Runtime tests for output normalization and fallback behavior.
- API test for `/chat` returning valid `ChatResponse` with both runtimes where possible.

Frontend:

- TypeScript build.
- Component-level checks for agent response rendering.
- Manual browser verification at desktop and mobile widths.
- Confirm no text overlaps in summary cards, agent cards, buttons, and table controls.

End-to-end:

- Start server and client locally.
- Ask CFO for a monthly financial health check.
- Confirm the response includes a natural-language answer plus structured findings/actions/audit data.
- Confirm the UI renders the structured response without layout breaks.

## Out Of Scope For First Phase

- Full authentication and multi-user permission model beyond the current `demo` user flow.
- Full investment advisory engine.
- Automatic trading, brokerage integration, or external account writes.
- Replacing the database schema unless required by structured agent history.
- Removing the existing LangGraph runtime before DeepAgents is verified.

## Open Decisions For Implementation Planning

- Whether to store agent structured outputs in the existing chat history table or add an `agent_runs` table later.
- Whether the first DeepAgents implementation should use only deterministic tools or also expose file/context middleware for intermediate analysis artifacts.
- Exact model defaults for local Ollama versus OpenAI-compatible providers.

These decisions can be resolved in the implementation plan without changing the approved product direction.
