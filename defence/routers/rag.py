"""
RAG Router

Endpoints for book ingestion and retrieval-augmented generation queries.
"""
from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from database.db import get_session
from schemas.rag import (
    IngestionRequest,
    IngestionStatusResponse,
    RAGQueryRequest,
    RAGQueryResponse,
)
from services.book_service import BookService
from services.rag.chunking_service import ChunkingService
from services.rag.embedding_service import EmbeddingService
from services.rag.pdf_loader import PDFLoaderService
from services.rag.protocols import VectorStore
from services.rag.rag_service import RAGService
from services.rag.vector_store_service import SupabaseVectorStoreService
from services.supabase_storage import SupabaseStorageService, get_storage_service

router = APIRouter(prefix="/rag", tags=["RAG"])


#  Dependency wiring 

def get_rag_service(
    session: Session = Depends(get_session),
    storage: SupabaseStorageService = Depends(get_storage_service),
) -> RAGService:
    embedding_svc = EmbeddingService()
    pdf_loader = PDFLoaderService(storage)
    chunker = ChunkingService()
    vector_store: VectorStore = SupabaseVectorStoreService(
        embedding_service=embedding_svc,
    )
    book_service = BookService(session, storage)
    return RAGService(
        session=session,
        book_service=book_service,
        pdf_loader=pdf_loader,
        chunker=chunker,
        vector_store=vector_store,
    )


# Ingestion 

@router.post(
    "/ingest",
    response_model=IngestionStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a book's PDF into the vector store",
)
def ingest_book(
    request: IngestionRequest,
    service: RAGService = Depends(get_rag_service),
) -> IngestionStatusResponse:
    """
    Download the book's PDF, extract text, chunk it, generate embeddings,
    and store the vectors in the configured vector store.

    Set ``force=true`` to re-ingest a book that was already processed.
    """
    return service.ingest_book(request.book_id, force=request.force)


@router.get(
    "/ingest/{book_id}/status",
    response_model=IngestionStatusResponse,
    summary="Check ingestion status for a book",
)
def get_ingestion_status(
    book_id: int,
    service: RAGService = Depends(get_rag_service),
) -> IngestionStatusResponse:
    return service.get_ingestion_status(book_id)


#  Query 

@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="Ask a question against ingested books",
)
async def query_books(
    request: RAGQueryRequest,
    service: RAGService = Depends(get_rag_service),
) -> RAGQueryResponse:
    """
    Embed the question, retrieve the most relevant book chunks via
    cosine similarity, and pass them as context to the LLM for a
    grounded answer.
    """
    return await service.query(request)
