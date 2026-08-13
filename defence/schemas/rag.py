from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


#  Ingestion 

class IngestionRequest(BaseModel):
    """Request body for triggering book ingestion."""
    book_id: int
    force: bool = Field(
        default=False,
        description="Re-ingest even if the book was already processed",
    )


class IngestionStatusResponse(BaseModel):
    """Current ingestion state for a book."""
    book_id: int
    status: str
    total_chunks: int
    total_pages: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


#  RAG Query 

class RAGQueryRequest(BaseModel):
    """Query the RAG pipeline."""
    query: str = Field(..., min_length=1, max_length=2000)
    book_id: Optional[int] = Field(
        default=None,
        description="Restrict retrieval to a single book",
    )
    top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    # LLM overrides
    model: Optional[str] = None
    temperature: Optional[float] = Field(default=1.0, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=100, ge=1)


class RAGChunkSource(BaseModel):
    """One retrieved chunk returned alongside the answer."""
    content: str
    book_id: int
    book_title: str
    page_number: Optional[int] = None
    chunk_index: int
    similarity: float


class RAGQueryResponse(BaseModel):
    """Full RAG answer with provenance."""
    answer: str
    sources: list[RAGChunkSource]
    model: str
    provider: str
