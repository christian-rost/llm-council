-- XQT5AIs Database Schema for Supabase
-- Run this in the Supabase SQL Editor

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(32) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conversations
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Messages (User + Assistant in one table)
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT,
    stage1 JSONB,
    stage2 JSONB,
    stage3 JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX idx_conversations_user ON conversations(user_id, created_at DESC);

-- App Settings (Key-Value for Chairman, Council models, etc.)
CREATE TABLE app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Default values
INSERT INTO app_settings (key, value) VALUES
    ('chairman_model', '"google/gemini-3-pro-preview"'),
    ('council_models', '["openai/gpt-5.1", "google/gemini-3-pro-preview", "anthropic/claude-sonnet-4.5", "x-ai/grok-4"]');

-- API Keys for public REST API
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    key_hash TEXT NOT NULL,
    key_prefix VARCHAR(16) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    rate_limit INTEGER DEFAULT 5,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);

-- Provider API Keys (encrypted, for direct provider access)
CREATE TABLE provider_api_keys (
    provider VARCHAR(50) PRIMARY KEY,
    api_key_encrypted TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Token Usage Tracking
CREATE TABLE token_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,  -- nullable for API calls
    message_id UUID REFERENCES messages(id) ON DELETE CASCADE,            -- nullable for API calls
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,  -- nullable, for per-user stats
    api_key_id UUID,                          -- API key reference for public API calls
    source VARCHAR(10) DEFAULT 'chat' CHECK (source IN ('chat', 'api')),
    model VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    stage VARCHAR(10) NOT NULL CHECK (stage IN ('stage1', 'stage2', 'stage3', 'title')),
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated_cost_usd DECIMAL(10, 6),
    cached_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_token_usage_conversation ON token_usage(conversation_id);
CREATE INDEX idx_token_usage_created ON token_usage(created_at);
CREATE INDEX idx_token_usage_provider ON token_usage(provider, created_at);
