# repositories/

PostgreSQL persistence layer: connection management, schema, and data repositories.

## Files

| File | Description |
|------|-------------|
| `connection.py` | Connection pool management (psycopg_pool), auto-creates tables on first use |
| `profile_repo.py` | CRUD for `user_profiles` table |
| `chat_repo.py` | CRUD for `chat_history` table |
| `schema.sql` | Single source of truth for the full database schema (can be run manually via `psql`) |
| `__init__.py` | Re-exports all repository functions |

## Schema

### user_profiles

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT PK | Unique user identifier |
| `name` | TEXT | Display name |
| `occupation` | TEXT | User's occupation |
| `financial_goals` | JSONB | Array of goal strings |
| `risk_tolerance` | TEXT | `conservative` / `moderate` / `aggressive` |
| `cash_balance` | DOUBLE PRECISION | Cash/checking balance |
| `savings` | DOUBLE PRECISION | Savings deposits |
| `investments` | DOUBLE PRECISION | Investment assets |
| `liabilities` | DOUBLE PRECISION | Debts and liabilities |
| `monthly_income` | DOUBLE PRECISION | Monthly income |
| `monthly_expenses` | DOUBLE PRECISION | Monthly expenses |
| `notes` | TEXT | Free-form notes |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

### chat_history

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL PK | Auto-increment ID |
| `user_id` | TEXT | User who sent/received the message |
| `role` | TEXT | `user` or `assistant` |
| `content` | TEXT | Message content |
| `created_at` | TIMESTAMPTZ | When the message was created |

**Index:** `idx_chat_history_user_created_at` on `(user_id, created_at DESC)`

## Setup

The application auto-creates tables on first connection. To manually initialize:

```bash
psql -U personal_finance_user -d personal_finance -f backend/app/repositories/schema.sql
```

## Configuration

Set one of these environment variables:

```
POSTGRES_DSN=postgresql://personal_finance_user:personal_finance_password@localhost:15433/personal_finance
# or
DATABASE_URL=postgresql://personal_finance_user:personal_finance_password@localhost:15433/personal_finance
```

If neither is set, the app falls back to in-memory storage only (no persistence across restarts).
