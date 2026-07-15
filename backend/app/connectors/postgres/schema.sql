-- ============================================================
-- Finance AI - PostgreSQL Schema
-- ============================================================
-- This file is the single source of truth for the database schema.
-- The application auto-creates these tables on startup via db/connection.py,
-- but you can also run this file manually:
--
--   psql -U personal_finance_user -d personal_finance -f backend/app/connectors/postgres/schema.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- User profiles
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id         TEXT PRIMARY KEY,
    name            TEXT NOT NULL DEFAULT '',
    occupation      TEXT NOT NULL DEFAULT '',
    financial_goals JSONB NOT NULL DEFAULT '[]'::jsonb,
    risk_tolerance  TEXT NOT NULL DEFAULT 'moderate',
    cash_balance    DOUBLE PRECISION NOT NULL DEFAULT 0,
    savings         DOUBLE PRECISION NOT NULL DEFAULT 0,
    investments     DOUBLE PRECISION NOT NULL DEFAULT 0,
    liabilities     DOUBLE PRECISION NOT NULL DEFAULT 0,
    monthly_income  DOUBLE PRECISION NOT NULL DEFAULT 0,
    monthly_expenses DOUBLE PRECISION NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    preferences     JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Preferences column for databases created before agent-workspace-linkage
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferences JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Chat history
CREATE TABLE IF NOT EXISTS chat_history (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_history_user_created_at
    ON chat_history (user_id, created_at DESC);

-- Office session columns for databases created before office-sessions
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS session_id TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS request_id TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_chat_history_user_session_created_at
    ON chat_history (user_id, session_id, created_at);

-- My Office CFO meeting sessions
CREATE TABLE IF NOT EXISTS office_sessions (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'active',
    last_message_preview TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_office_sessions_user_updated_at
    ON office_sessions (user_id, updated_at DESC);

-- Current-chat session memory for multi-turn finance context
CREATE TABLE IF NOT EXISTS session_memory (
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL DEFAULT 'default',
    memory      JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_session_memory_updated_at
    ON session_memory (updated_at DESC);

-- Transactions imported from statement processors or future bank connectors
CREATE TABLE IF NOT EXISTS transactions (
    id               BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL,
    date             DATE NOT NULL,
    month            TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    counterparty     TEXT NOT NULL DEFAULT '',
    amount           DOUBLE PRECISION NOT NULL,
    gross_amount     DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency         TEXT NOT NULL DEFAULT 'CNY',
    balance          DOUBLE PRECISION,
    direction        TEXT NOT NULL DEFAULT '',
    type             TEXT NOT NULL DEFAULT '',
    category         TEXT NOT NULL DEFAULT 'other',
    status           TEXT NOT NULL DEFAULT '',
    payment_method   TEXT NOT NULL DEFAULT '',
    external_id      TEXT NOT NULL DEFAULT '',
    merchant_order_id TEXT NOT NULL DEFAULT '',
    source           TEXT NOT NULL DEFAULT 'manual',
    source_file      TEXT NOT NULL DEFAULT '',
    source_format    TEXT NOT NULL DEFAULT '',
    note             TEXT NOT NULL DEFAULT '',
    is_duplicate     BOOLEAN NOT NULL DEFAULT false,
    duplicate_reason TEXT NOT NULL DEFAULT '',
    duplicate_of     TEXT NOT NULL DEFAULT '',
    raw              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup columns for databases created before statement-sources-expansion
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS duplicate_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS duplicate_of TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_transactions_user_date
    ON transactions (user_id, date DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_source_external
    ON transactions (user_id, source, external_id);

-- Statement import metadata for Settings status, audit, and troubleshooting
CREATE TABLE IF NOT EXISTS statement_import_records (
    import_id      TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    source_file    TEXT NOT NULL DEFAULT '',
    source_format  TEXT NOT NULL DEFAULT 'csv',
    imported_count INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'succeeded',
    error          TEXT NOT NULL DEFAULT '',
    sample         JSONB NOT NULL DEFAULT '[]'::jsonb,
    quality_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Quality report column for databases created before specialist-runtime-convergence
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS quality_report JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_statement_import_records_user_created_at
    ON statement_import_records (user_id, created_at DESC);

-- Analysis snapshots for frontend reporting
CREATE TABLE IF NOT EXISTS analysis_runs (
    id            BIGSERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL,
    period_start  DATE,
    period_end    DATE,
    monthly_totals JSONB NOT NULL DEFAULT '[]'::jsonb,
    input         JSONB NOT NULL DEFAULT '{}'::jsonb,
    output        JSONB NOT NULL DEFAULT '{}'::jsonb,
    source        TEXT NOT NULL DEFAULT 'manual',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created_at
    ON analysis_runs (user_id, created_at DESC, id DESC);

-- Immutable exchange-rate snapshots used by AI cost reporting
CREATE TABLE IF NOT EXISTS exchange_rate_snapshots (
    billing_currency    TEXT NOT NULL,
    reporting_currency  TEXT NOT NULL,
    exchange_rate       NUMERIC(28, 12) NOT NULL CHECK (exchange_rate > 0),
    exchange_rate_date  DATE NOT NULL,
    exchange_rate_source TEXT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (
        billing_currency,
        reporting_currency,
        exchange_rate_date,
        exchange_rate_source
    )
);

CREATE INDEX IF NOT EXISTS idx_exchange_rate_lookup
    ON exchange_rate_snapshots (
        billing_currency,
        reporting_currency,
        exchange_rate_date DESC
    );

-- Agent harness run ledger for audit and replay
CREATE TABLE IF NOT EXISTS agent_run_records (
    request_id        TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    entrypoint        TEXT NOT NULL,
    runtime_requested TEXT NOT NULL,
    runtime_used      TEXT,
    model_name        TEXT,
    output_contract   TEXT,
    audit_status      TEXT,
    error_type        TEXT,
    request_count     INTEGER NOT NULL DEFAULT 0,
    model_response_count INTEGER NOT NULL DEFAULT 0,
    input_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_status       TEXT NOT NULL DEFAULT 'not_applicable',
    billing_totals    JSONB NOT NULL DEFAULT '[]'::jsonb,
    reporting_currency TEXT NOT NULL DEFAULT 'USD',
    reporting_total_cost NUMERIC(28, 12),
    record            JSONB NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_run_records_user_created_at
    ON agent_run_records (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_run_records_entrypoint_created_at
    ON agent_run_records (entrypoint, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_run_records_error_created_at
    ON agent_run_records (error_type, created_at DESC);

-- V2 cost columns for databases created before multi-currency accounting.
ALTER TABLE agent_run_records ADD COLUMN IF NOT EXISTS cost_status TEXT NOT NULL DEFAULT 'not_applicable';
ALTER TABLE agent_run_records ADD COLUMN IF NOT EXISTS billing_totals JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE agent_run_records ADD COLUMN IF NOT EXISTS reporting_currency TEXT NOT NULL DEFAULT 'USD';
ALTER TABLE agent_run_records ADD COLUMN IF NOT EXISTS reporting_total_cost NUMERIC(28, 12);

-- Category correction feedback (for improving categorization accuracy)
-- CREATE TABLE IF NOT EXISTS category_corrections (
--     id              BIGSERIAL PRIMARY KEY,
--     user_id         TEXT NOT NULL,
--     description     TEXT NOT NULL,
--     original_cat    TEXT NOT NULL,
--     corrected_cat   TEXT NOT NULL,
--     created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
