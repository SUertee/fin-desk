# agents/

CFO-first agent definitions for the personal finance backend.

## Current Shape

The default `/chat` path is owned by the CFO agent. Specialist behavior for
chat is currently exposed through controlled tools, so the CFO owns the final
answer instead of freely handing the conversation to another agent. The
`/analyze` path is backed by a dedicated Analysis Specialist agent.

## Files

| Path | Description |
|------|-------------|
| `cfo/agent.py` | OpenAI Agents SDK CFO agent factory |
| `cfo/prompt.md` | CFO system instructions |
| `cfo/schema.py` | CFO output schema helpers |
| `orchestrator.py` | Stable application entrypoint for chat, profile, and memory handling |
| `specialists/analysis_agent.py` | OpenAI Agents SDK specialist for `/analyze` JSON output |

## Runtime Boundary

Runtime execution lives in `app/runtime/`. Agent modules should not directly
query repositories or database sessions; data access should flow through tools,
services, and repositories.
