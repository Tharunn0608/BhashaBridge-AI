-- BhashaBridge AI database schema (SQLite).
-- Only text conversation history is stored. Voice recordings are NEVER saved.
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    language    TEXT,
    source      TEXT,              -- 'llm' | 'faq' | 'fallback' for assistant replies
    created_at  TEXT NOT NULL      -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id);
