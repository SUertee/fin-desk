# FinDesk Client

React + Vite client for FinDesk — A Personal Finance Agent Team.

## Running the client

Run `npm install` to install dependencies.

Run `npm run dev` to start the development server.

Default local URL: `http://localhost:18001`.

By default the app expects:

- `VITE_LLM_ENDPOINT=http://localhost:8000/chat`
- `VITE_API_BASE_URL=http://localhost:18000`
- `VITE_N8N_WEBHOOK_URL=http://localhost:5678/webhook-test/finance-analyze-pdf`

## Agent Harness Replay

The dashboard includes an Agent Harness Replay panel backed by:

- `GET /agent-runs/user/{user_id}`
- `GET /agent-runs/{request_id}/replay?case_id=...`

The panel shows selected agents, tool calls, handoffs, output validations,
token usage, configured cost estimates, server-side run filters, pagination,
date range search, and optional fixture eval results. It requires the backend
run ledger to be persisted, so set `POSTGRES_DSN` or `DATABASE_URL` on the
backend before running chat or analysis requests.
