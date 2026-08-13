-- ============================================================
-- RAG setup for 768-dimension embeddings
-- (Google text-embedding-004 or Ollama nomic-embed-text)
-- ============================================================
-- Use this INSTEAD of rag_setup.sql when EMBEDDING_DIMENSIONS=768.
-- Safe to run on a fresh DB or to convert an existing 1536 setup —
-- it drops and recreates the vector table/function at 768 dims.
-- Run once in the Supabase dashboard -> SQL Editor.
-- ============================================================

-- 1. pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Recreate the chunks table at vector(768).
--    DROP is safe here: the table only holds re-creatable embeddings.
DROP TABLE IF EXISTS book_chunks CASCADE;

CREATE TABLE book_chunks (
    id          text        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    content     text        NOT NULL,
    metadata    jsonb       DEFAULT '{}'::jsonb,
    embedding   vector(768)                          -- matches 768-dim models
);

-- 3. HNSW cosine index for fast similarity search
CREATE INDEX idx_book_chunks_embedding
    ON book_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 4. GIN index on metadata (for filtering by book_id, etc.)
CREATE INDEX idx_book_chunks_metadata
    ON book_chunks
    USING gin (metadata);

-- 5. Similarity-search RPC at 768 dims.
--    (Postgres ignores the typmod on function args, so create-or-replace
--     cleanly swaps any previous 1536 version with the same signature.)
CREATE OR REPLACE FUNCTION match_book_chunks(
    query_embedding vector(768),
    match_count     int   DEFAULT 5,
    filter          jsonb DEFAULT '{}'::jsonb
)
RETURNS TABLE (
    id          text,
    content     text,
    metadata    jsonb,
    similarity  float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        bc.id,
        bc.content,
        bc.metadata,
        1 - (bc.embedding <=> query_embedding) AS similarity
    FROM book_chunks bc
    WHERE bc.metadata @> filter
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 6. Ingestion tracking table (also created by the app at startup; IF NOT EXISTS is safe)
CREATE TABLE IF NOT EXISTS bookingestion (
    id              serial      PRIMARY KEY,
    book_id         integer     NOT NULL REFERENCES book(id) ON DELETE CASCADE,
    status          varchar(20) NOT NULL DEFAULT 'pending',
    total_chunks    integer     NOT NULL DEFAULT 0,
    total_pages     integer     NOT NULL DEFAULT 0,
    error_message   text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(book_id)
);
