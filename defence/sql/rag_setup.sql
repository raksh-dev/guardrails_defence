-- ============================================================
-- RAG Pipeline – Database Setup for Supabase (pgvector)
-- ============================================================
-- Run this script once in the Supabase SQL Editor before using
-- the /rag endpoints.
-- ============================================================

-- 1. Enable the pgvector extension (requires superuser on
--    self-hosted PG; already available in Supabase).
CREATE EXTENSION IF NOT EXISTS vector;


-- 2. Book chunks table – stores text + embedding for each chunk.
--    The 'id' column uses text to stay compatible with LangChain's
--    SupabaseVectorStore which generates UUID strings client-side.
CREATE TABLE IF NOT EXISTS book_chunks (
    id          text        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    content     text        NOT NULL,
    metadata    jsonb       DEFAULT '{}'::jsonb,
    embedding   vector(1536)                         -- matches text-embedding-3-small
);


-- 3. HNSW index for fast approximate nearest-neighbour search
--    using cosine distance.  HNSW offers good recall without
--    requiring periodic index rebuilds (unlike IVFFlat).
CREATE INDEX IF NOT EXISTS idx_book_chunks_embedding
    ON book_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);


-- 4. GIN index on metadata for fast JSONB containment queries
--    (e.g. filtering by book_id).
CREATE INDEX IF NOT EXISTS idx_book_chunks_metadata
    ON book_chunks
    USING gin (metadata);


-- 5. Similarity search RPC function called by LangChain's
--    SupabaseVectorStore.similarity_search_with_relevance_scores().
--
--    Parameters:
--      query_embedding  – the embedded user question
--      match_count      – how many results to return (top-k)
--      filter           – JSONB containment filter, e.g. {"book_id":1}
--
--    Returns rows ordered by cosine similarity (1 = identical).
CREATE OR REPLACE FUNCTION match_book_chunks(
    query_embedding vector(1536),
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


-- 6. Book ingestion tracking table.
--    One row per book; tracks status, chunk count, page count.
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
