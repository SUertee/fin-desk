# api/

FastAPI route handlers, organized by domain. Each file defines an `APIRouter` that is mounted in `app.main`.

## Files

| File | Description |
|------|-------------|
| `health.py` | `GET /health` and `GET /schema` - health check + JSON schema for frontend |
| `analyze.py` | `POST /analyze` - original transaction analysis pipeline |
| `chat.py` | `POST /chat`, `GET /chat/history/{user_id}`, `DELETE /chat/history/{user_id}` - multi-agent chat |
| `profile.py` | `GET /profile/{user_id}`, `PUT /profile/{user_id}` - user profile CRUD |
| `transactions.py` | `GET /transactions/{user_id}`, `GET /analysis-runs/latest/{user_id}` - dashboard data from local Postgres |
| `agent_runs.py` | `GET /agent-runs/{request_id}`, `GET /agent-runs/{request_id}/replay`, `GET /agent-runs/user/{user_id}` - agent run ledger and replay |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns backend status, version, and available runtime components |
| GET | `/schema` | JSON Schema for the analysis response format |
| POST | `/analyze` | Run full analysis pipeline on transactions |
| POST | `/chat` | Send a message to the multi-agent system |
| GET | `/chat/history/{user_id}` | Retrieve chat history |
| DELETE | `/chat/history/{user_id}` | Clear chat history |
| GET | `/profile/{user_id}` | Get user profile |
| PUT | `/profile/{user_id}` | Update user profile fields |
| GET | `/transactions/{user_id}` | List imported transactions for the dashboard |
| GET | `/analysis-runs/latest/{user_id}` | Return the latest imported summary snapshot |
| GET | `/agent-runs/{request_id}` | Return a full agent run record for replay/debugging |
| GET | `/agent-runs/{request_id}/replay` | Replay a persisted run record, optionally against an eval `case_id` |
| GET | `/agent-runs/user/{user_id}` | List paginated agent run records for a user, with optional `offset`, `entrypoint`, `runtime_used`, `audit_status`, `has_error`, `created_from`, and `created_to` filters |

## Adding a New Endpoint

1. Create a new file or add to an existing one
2. Define a `router = APIRouter()`
3. Add route handlers
4. Mount in `app.main`: `app.include_router(your_router)`
