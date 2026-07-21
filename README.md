# FinDesk

**A Personal Finance Agent Team**

FinDesk turns raw statement exports (Alipay, WeChat Pay, bank PDFs) into a reconciled personal ledger, then puts a CFO-led agent team on top of it — with typed handoffs, audit gating, and a replayable run ledger for every answer.

## Overview

Most personal-finance tools stop at charts. FinDesk exists to answer the next question — *"so what should I do?"* — and to make every answer inspectable. A self-hosted agent runtime routes each request through policy, bounded tools, and specialist agents; an auditor reviews the evidence before the response is composed; and every run persists a trace you can replay.

The project is equally an exercise in AI engineering discipline: statement parsers reconcile to the payment platforms' own summary figures exactly, cross-source duplicates are flagged with recorded reasons instead of silently dropped, and agent behavior is covered by offline eval fixtures that run in CI without live model calls.

FinDesk is intentionally a single-user, self-hosted agent team runtime rather
than a SaaS control plane. Capabilities are registered statically in-process;
optional providers are configured locally and remain behind typed connectors,
policy checks, and audit boundaries.

## Core Features

- **Statement import** — dedicated parsers for Alipay CSV (GB18030), WeChat Pay XLSX, and ICBC bank PDFs, with source auto-detection, idempotent re-import, and cross-source duplicate detection (card-tail and counterparty matching)
- **Transaction analysis** — category rollups, anomaly detection, and monthly cash-flow trends over the reconciled ledger
- **Budget health review** — expense-ratio evaluation against profile income with explicit `data_limited` states instead of fabricated numbers
- **CFO brief** — an agent-generated judgment sentence, summary cards, and prioritized actions drive the workspace homepage
- **Multi-agent chat** — CFO-first conversation with specialist handoffs, per-finding agent attribution, and a "view trace" link on every reply
- **Import quality evidence** — each import produces a persisted quality report (category confidence, skip reasons, duplicates) that agents cite as caveats
- **User profile and memory** — persisted preferences (reply language, tone, evidence level) consumed by the response composer; bounded session memory shared across agents
- **Full-stack dashboard** — spending calendar heatmap with day drill-down, trends, category breakdowns, and a bilingual (zh/en) interface

## Agent Team

| Agent | Role | Activation |
|---|---|---|
| **CFO** | Lead agent; owns the final user-facing answer and composes specialist evidence | Every run |
| **Expense Analyst** | Spending structure, top categories, anomaly review; cites import-quality caveats | Spending intent |
| **Budget Coach** | Expense-ratio evaluation and low-friction budget actions | Budget intent |
| **Auditor** | Reviews peer outputs and evidence quality; flags unsupported claims before composition | Audit policy (most runs) |
| **Market Context** | External market/news facts with mandatory source URLs and timestamps | Market intent **and** an explicit config gate; never by default |

Specialists are `run(SpecialistInput) -> SpecialistAgentOutput` modules resolved from a registry by a single `SpecialistRunner`, which owns dispatch, output-contract validation, latency, and failure mapping. The registry is the seam where an LLM-backed implementation can replace a deterministic one without touching the orchestrator, contracts, traces, or evals.

## Architecture Overview

```text
User
 └─ React/Vite client (workspace, docked CFO chat, settings)
     └─ FastAPI backend (thin routes)
         └─ Finance runtime (CFO-first orchestration)
             ├─ Runtime policy         intent → specialists, audit gating, budgets
             ├─ Execution plan         bounded tool steps + handoffs
             ├─ Bounded tools          finance context, snapshots, anomaly,
             │                         cashflow, import-quality report
             ├─ SpecialistRunner       registry dispatch + contract validation
             │   └─ Specialists        expense / budget / auditor / market (gated)
             ├─ Response composer      preferences-aware reply (zh/en, tone, evidence)
             └─ Trace collector        → run ledger (audit status, tools, cost)
                 └─ PostgreSQL + pgvector
                     (ledger, profiles, memory, import records, run records)
```

## Data Flow

1. A chat message (or workspace-brief request) hits a route, which loads the user's transactions, profile, and memory context.
2. **Runtime policy** classifies intent and risk: which specialists are required, whether audit is mandatory, and the tool-call budget. A typed `requested_specialist` hint can add (never remove) a specialist.
3. The **planner** emits an execution plan; the **bounded tool executor** runs tool steps (finance context, expense/budget snapshots, import-quality report) and records each call in the trace.
4. The **SpecialistRunner** executes handoffs from the registry; each output is validated against the `SpecialistAgentOutput` contract — invalid output fails the handoff visibly.
5. The **auditor** reviews peer outputs; the **response composer** builds the reply honoring user preferences (language, tone, evidence level).
6. The full run — selected agents, tool calls, handoffs, validations, audit status, latency, cost estimate — persists to the **run ledger**, addressable by the `request_id` returned to the client.

## Tech Stack

- **Frontend**: React 18, Vite, TypeScript, Recharts; lightweight zh/en i18n layer
- **Backend**: FastAPI, Pydantic v2 contracts at every boundary
- **Database**: PostgreSQL 16 with pgvector (vector retrieval planned; schema migrations are idempotent DDL)
- **AI layer**: self-hosted deterministic agent runtime by default; OpenAI (Agents SDK) as an optional provider adapter isolated in `runtime/llm/`
- **Parsing**: GB18030 decoding, openpyxl (WeChat XLSX), pypdf (bank PDF text extraction)
- **Infrastructure**: Docker Compose (pgvector + backend), GitHub Actions harness CI

## API Overview

```text
GET    /health                          runtime identity and component status
GET    /schema                          analysis output schema
POST   /analyze                         transaction analysis (typed output contract)
POST   /chat                            CFO chat (returns request_id for trace lookup)
GET    /workspace/brief/{user_id}       agent-generated workspace brief
GET    /profile/{user_id}               profile + preferences
PUT    /profile/{user_id}               update profile + preferences
GET    /chat/history/{user_id}          chat history
DELETE /chat/history/{user_id}          clear chat history
GET    /transactions/{user_id}          ledger (optional date_from/date_to)
GET    /transactions/daily/{user_id}    per-day totals for the calendar (?month=)
POST   /statement-import/import         statement upload (CSV/XLSX/PDF)
GET    /analysis-runs/latest/{user_id}  latest analysis snapshot
GET    /agent-runs/{request_id}         run-ledger record / trace projection
```

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 18000
```

### Client

```bash
cd web
npm install
npm run dev        # http://localhost:18001
```

### Docker Compose

```bash
docker compose up --build
# db:      127.0.0.1:15433 (pgvector/pgvector:pg16)
# backend: http://localhost:18000
```

The backend applies `connectors/postgres/schema.sql` automatically on startup.

### Tests and Harness CI

`.github/workflows/harness-ci.yml` runs the backend test suite, module compilation, the offline trace-regression sample, and the web build. Locally:

```bash
cd backend && python -m pytest tests -q
cd web && npm run build
```

## Environment Variables

| Variable | Purpose |
|---|---|
| `POSTGRES_DSN` | database DSN (default local: `postgresql://...@localhost:15433/personal_finance`) |
| `OPENAI_API_KEY` | optional — enables the OpenAI Agents SDK path for `/analyze` |
| `OPENAI_AGENT_MODEL`, `OPENAI_AGENT_MAX_TURNS` | OpenAI adapter tuning |
| `OPENAI_*_COST_PER_1M` | run-ledger cost estimation rates |
| `MARKET_CONTEXT_ENABLED` | config gate for the Market Context specialist (default off) |
| `NEWS_API_KEY` | optional — market/news lookups when the gate is on |
| `VITE_API_BASE_URL` | client → backend base URL (default `http://localhost:18000`) |

## Project Status

Actively evolving. The current focus is personal finance analysis and agent orchestration: multi-source statement ingestion with reconciliation guarantees, the CFO-first runtime with audited specialist handoffs, and workspace surfaces that render agent output rather than client-side heuristics. Single-user local deployment; no authentication layer yet.

## Roadmap

- **Retrieval layer**: typed transaction query tool (structured filters/aggregation), semantic search over transaction history, and a cited finance knowledge base on pgvector
- **Market connectivity**: FX rates, response caching, and outbound-call budgets behind the existing specialist gate
- **Schema-driven runtime config**: one Pydantic config schema generating both validation and a visual settings form
- **Email statement connector**: auto-ingest the bill exports Alipay/WeChat deliver by email
- **Richer evals**: grow the offline fixture set covering retrieval grounding and citation behavior
- **Deployment setup**: optional single-host deployment guide

## Disclaimer

FinDesk is a personal finance analysis and education tool. It does not provide professional financial, investment, tax, or legal advice.
