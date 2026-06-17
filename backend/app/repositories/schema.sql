-- ============================================================
-- Finance AI - PostgreSQL Schema
-- ============================================================
-- This file is the single source of truth for the database schema.
-- The application auto-creates these tables on startup via db/connection.py,
-- but you can also run this file manually:
--
--   psql -U personal_finance_user -d personal_finance -f backend/app/repositories/schema.sql
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
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
    raw              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date
    ON transactions (user_id, date DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_source_external
    ON transactions (user_id, source, external_id);

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

-- Category correction feedback (for improving categorization accuracy)
-- CREATE TABLE IF NOT EXISTS category_corrections (
--     id              BIGSERIAL PRIMARY KEY,
--     user_id         TEXT NOT NULL,
--     description     TEXT NOT NULL,
--     original_cat    TEXT NOT NULL,
--     corrected_cat   TEXT NOT NULL,
--     created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
