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

-- Opaque browser sessions. Raw session tokens are never persisted.
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    email       TEXT NOT NULL,
    csrf_token  TEXT NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_expires
    ON auth_sessions (user_id, expires_at DESC);

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
    cost_preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Preferences column for databases created before agent-workspace-linkage
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferences JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS cost_preferences JSONB NOT NULL DEFAULT '{}'::jsonb;

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

-- Reviewed finance guidance. Live web-search results are not written here.
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id       TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    source_url        TEXT NOT NULL,
    source_authority  TEXT NOT NULL,
    source_type       TEXT NOT NULL
        CHECK (source_type IN ('official_guidance', 'internal_policy', 'user_document')),
    jurisdiction      TEXT NOT NULL,
    language          TEXT NOT NULL,
    source_updated_at DATE,
    reviewed_at       DATE NOT NULL,
    review_after      DATE NOT NULL CHECK (review_after >= reviewed_at),
    tags              JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_hash      TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_review_after
    ON knowledge_documents (review_after, document_id);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id      TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    ordinal       INTEGER NOT NULL CHECK (ordinal >= 0),
    heading       TEXT NOT NULL,
    content       TEXT NOT NULL,
    content_hash  TEXT NOT NULL CHECK (length(content_hash) = 64),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document
    ON knowledge_chunks (document_id, ordinal);

ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
    GENERATED ALWAYS AS (
        to_tsvector('simple', COALESCE(heading, '') || ' ' || COALESCE(content, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_search_vector
    ON knowledge_chunks USING GIN (search_vector);

-- Optional provider-neutral embeddings for reviewed knowledge. The unbounded
-- vector column keeps model dimensions out of the domain schema; V1 uses exact
-- cosine search because the reviewed corpus is intentionally small.
CREATE TABLE IF NOT EXISTS knowledge_chunk_embeddings (
    chunk_id      TEXT NOT NULL REFERENCES knowledge_chunks(chunk_id) ON DELETE CASCADE,
    provider_id   TEXT NOT NULL,
    model_id      TEXT NOT NULL,
    dimension     INTEGER NOT NULL CHECK (dimension BETWEEN 1 AND 4096),
    embedding     VECTOR NOT NULL,
    content_hash  TEXT NOT NULL CHECK (length(content_hash) = 64),
    embedded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chunk_id, provider_id, model_id),
    CHECK (vector_dims(embedding) = dimension)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_provider
    ON knowledge_chunk_embeddings (provider_id, model_id, dimension, chunk_id);

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
    ingestion_channel TEXT NOT NULL DEFAULT 'upload',
    content_hash   TEXT NOT NULL DEFAULT '',
    stored_path    TEXT NOT NULL DEFAULT '',
    detected_source TEXT NOT NULL DEFAULT '',
    origin_key     TEXT NOT NULL DEFAULT '',
    origin_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Quality report column for databases created before specialist-runtime-convergence
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS quality_report JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS ingestion_channel TEXT NOT NULL DEFAULT 'upload';
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS stored_path TEXT NOT NULL DEFAULT '';
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS detected_source TEXT NOT NULL DEFAULT '';
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS origin_key TEXT NOT NULL DEFAULT '';
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS origin_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE statement_import_records ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_statement_import_records_user_created_at
    ON statement_import_records (user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_statement_import_records_user_hash
    ON statement_import_records (user_id, content_hash)
    WHERE content_hash <> '';

CREATE TABLE IF NOT EXISTS statement_import_settings (
    user_id             TEXT PRIMARY KEY,
    folder_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    folder_subdirectory TEXT NOT NULL DEFAULT '',
    auto_commit         BOOLEAN NOT NULL DEFAULT TRUE,
    email_enabled       BOOLEAN NOT NULL DEFAULT FALSE,
    email_mailbox       TEXT NOT NULL DEFAULT 'INBOX',
    email_allowed_senders JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

-- Current investment account state synchronized by future connectors/imports
CREATE TABLE IF NOT EXISTS investment_accounts (
    user_id       TEXT NOT NULL,
    account_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    account_type  TEXT NOT NULL,
    provider      TEXT NOT NULL DEFAULT 'manual',
    base_currency TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    as_of         TIMESTAMPTZ NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_investment_accounts_user_updated_at
    ON investment_accounts (user_id, updated_at DESC);

-- Latest aggregate positions per account; replacement is connector-scoped
CREATE TABLE IF NOT EXISTS investment_positions (
    user_id            TEXT NOT NULL,
    account_id         TEXT NOT NULL,
    symbol             TEXT NOT NULL,
    asset_type         TEXT NOT NULL,
    quantity           NUMERIC(28, 12) NOT NULL CHECK (quantity > 0),
    average_cost_amount NUMERIC(28, 12),
    average_cost_currency TEXT,
    as_of              TIMESTAMPTZ NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, account_id, symbol, asset_type),
    FOREIGN KEY (user_id, account_id)
        REFERENCES investment_accounts (user_id, account_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_investment_positions_user_account
    ON investment_positions (user_id, account_id, symbol);

-- User-curated research watchlist. These rows are not investment holdings.
CREATE TABLE IF NOT EXISTS investment_watchlist_items (
    user_id       TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    asset_type    TEXT NOT NULL,
    note          TEXT NOT NULL DEFAULT '',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, symbol, asset_type)
);

CREATE INDEX IF NOT EXISTS idx_investment_watchlist_user_updated_at
    ON investment_watchlist_items (user_id, updated_at DESC);

-- Hypothetical research scenarios. They never represent brokerage holdings.
CREATE TABLE IF NOT EXISTS investment_scenarios (
    user_id             TEXT NOT NULL,
    scenario_id         TEXT NOT NULL,
    name                TEXT NOT NULL,
    reporting_currency  TEXT NOT NULL,
    starting_cash_amount NUMERIC(28, 12) CHECK (starting_cash_amount >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, scenario_id)
);

CREATE INDEX IF NOT EXISTS idx_investment_scenarios_user_updated_at
    ON investment_scenarios (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS investment_scenario_positions (
    user_id       TEXT NOT NULL,
    scenario_id   TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    asset_type    TEXT NOT NULL,
    quantity      NUMERIC(28, 12) NOT NULL CHECK (quantity > 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, scenario_id, symbol, asset_type),
    FOREIGN KEY (user_id, scenario_id)
        REFERENCES investment_scenarios (user_id, scenario_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_investment_scenario_positions_user_scenario
    ON investment_scenario_positions (user_id, scenario_id, symbol);

-- Immutable, sourced market facts used for reproducible as-of valuation
CREATE TABLE IF NOT EXISTS market_quote_snapshots (
    symbol        TEXT NOT NULL,
    asset_type    TEXT NOT NULL,
    price         NUMERIC(28, 12) NOT NULL CHECK (price > 0),
    currency      TEXT NOT NULL,
    quote_as_of   TIMESTAMPTZ NOT NULL,
    timestamp_basis TEXT NOT NULL DEFAULT 'provider_time',
    quote_source  TEXT NOT NULL,
    venue         TEXT NOT NULL DEFAULT '',
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, asset_type, quote_as_of, quote_source, venue)
);

CREATE INDEX IF NOT EXISTS idx_market_quote_snapshots_lookup
    ON market_quote_snapshots (symbol, asset_type, quote_as_of DESC);

ALTER TABLE market_quote_snapshots
    ADD COLUMN IF NOT EXISTS timestamp_basis TEXT NOT NULL DEFAULT 'provider_time';

-- Replaceable response cache for normalized external market-data reads.
-- Immutable quote evidence remains in market_quote_snapshots.
CREATE TABLE IF NOT EXISTS market_data_cache (
    cache_key      TEXT PRIMARY KEY,
    operation      TEXT NOT NULL,
    provider       TEXT NOT NULL,
    payload        JSONB NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL,
    expires_at     TIMESTAMPTZ NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at > fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_market_data_cache_expiry
    ON market_data_cache (expires_at);

-- Replaceable TTL cache for allowlisted external web-research evidence.
CREATE TABLE IF NOT EXISTS web_research_cache (
    cache_key   TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    payload     JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at > fetched_at)
);

CREATE INDEX IF NOT EXISTS idx_web_research_cache_expiry
    ON web_research_cache (expires_at);

-- User-owned RSS subscriptions for the manually refreshed Finance Inbox.
CREATE TABLE IF NOT EXISTS content_subscriptions (
    id                  TEXT PRIMARY KEY,
    user_id             TEXT NOT NULL,
    name                TEXT NOT NULL,
    source_type         TEXT NOT NULL DEFAULT 'rss' CHECK (source_type = 'rss'),
    feed_url            TEXT NOT NULL,
    normalized_feed_url TEXT NOT NULL,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    last_refresh_status TEXT NOT NULL DEFAULT 'never'
        CHECK (last_refresh_status IN ('never', 'success', 'partial', 'failed')),
    last_refresh_at     TIMESTAMPTZ,
    last_success_at     TIMESTAMPTZ,
    last_error_code     TEXT,
    etag                TEXT,
    last_modified       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, normalized_feed_url)
);

CREATE INDEX IF NOT EXISTS idx_content_subscriptions_user_updated_at
    ON content_subscriptions (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_content_subscriptions_refresh
    ON content_subscriptions (user_id, enabled, last_refresh_at DESC);

-- One logical article per user. Full article bodies are intentionally absent.
CREATE TABLE IF NOT EXISTS inbox_items (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL,
    item_key       TEXT NOT NULL,
    canonical_url  TEXT,
    title          TEXT NOT NULL,
    excerpt        TEXT NOT NULL DEFAULT '',
    author         TEXT,
    published_at   TIMESTAMPTZ,
    fetched_at     TIMESTAMPTZ NOT NULL,
    content_hash   TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'unread'
        CHECK (status IN ('unread', 'read', 'saved', 'dismissed')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, item_key)
);

CREATE INDEX IF NOT EXISTS idx_inbox_items_user_status_created_at
    ON inbox_items (user_id, status, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_inbox_items_user_content_hash
    ON inbox_items (user_id, content_hash);

-- Preserve every feed that discovered an item after cross-feed deduplication.
CREATE TABLE IF NOT EXISTS inbox_item_sources (
    item_id          TEXT NOT NULL REFERENCES inbox_items(id) ON DELETE CASCADE,
    subscription_id  TEXT NOT NULL REFERENCES content_subscriptions(id),
    source_name      TEXT NOT NULL,
    feed_entry_id    TEXT,
    discovered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (item_id, subscription_id)
);

CREATE INDEX IF NOT EXISTS idx_inbox_item_sources_subscription
    ON inbox_item_sources (subscription_id, discovered_at DESC);

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
