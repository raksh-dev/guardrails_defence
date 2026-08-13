"""
RAG Service  -  main orchestrator

Two public entry points:

1. **ingest_book(book_id)**
   PDF -> pages -> chunks -> embeddings -> vector store

2. **query(RAGQueryRequest)**
   question -> embed -> similarity search -> build prompt -> LLM -> answer

All heavy lifting is delegated to specialised sub-services; this module
only handles coordination and error handling. The vector backend is
addressed through the abstract :class:`~services.rag.protocols.VectorStore`
Protocol so it can be swapped (e.g. Pinecone, Qdrant, Chroma) without
changing this file.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from core.config import settings
from core.exceptions import (
    BookFileNotFoundException,
    BookNotFoundException,
    BookNotIngestedException,
    GuardrailBlockedException,
    RAGIngestionException,
    RAGQueryException,
)
from services.guardrails import enforce, input_guard, output_guard
from models.book_embedding import BookIngestion, IngestionStatus
from schemas.chat import ChatMessage
from schemas.rag import (
    IngestionStatusResponse,
    RAGChunkSource,
    RAGQueryRequest,
    RAGQueryResponse,
)
from services.book_service import BookService
from services.langchain_llm_provider import build_llm_provider
from services.rag.chunking_service import ChunkingService
from services.rag.pdf_loader import PDFLoaderService
from services.rag.protocols import VectorStore

logger = logging.getLogger(__name__)

#  RAG system prompt 

RAG_SYSTEM_PROMPT = """\
You are a knowledgeable assistant that answers questions based on the \
provided book excerpts.

Instructions:
- Answer the question based ONLY on the provided context from the book(s).
- If the context doesn't contain enough information to answer, say so clearly.
- Cite the specific book title and page number(s) when referencing information.
- Be precise and factual in your answers.
- If multiple sources provide relevant information, synthesize them coherently.

Context from books:
{context}
"""


class RAGService:
    """Facade that exposes ingestion + query to the router layer."""

    def __init__(
        self,
        session: Session,
        book_service: BookService,
        pdf_loader: PDFLoaderService,
        chunker: ChunkingService,
        vector_store: VectorStore,
    ) -> None:
        self._session = session
        self._book_service = book_service
        self._pdf_loader = pdf_loader
        self._chunker = chunker
        self._vector_store = vector_store

    #  Ingestion 

    def ingest_book(
        self,
        book_id: int,
        force: bool = False,
    ) -> IngestionStatusResponse:
        """
        Full ingestion pipeline:
        1. Validate book & file existence (via BookService)
        2. Download PDF from storage
        3. Extract text per page (PyPDF)
        4. Chunk pages with the configured TextSplitter
        5. Batch-embed & store vectors via the VectorStore protocol
        """
        # 1  validate (delegate to BookService - single source of truth)
        book = self._book_service.get_by_id(book_id)
        if not book:
            raise BookNotFoundException()
        if not book.file_path:
            raise BookFileNotFoundException(
                f"Book '{book.title}' has no PDF file uploaded"
            )

        # 2  idempotency check
        ingestion = self._get_ingestion(book_id)
        if (
            ingestion
            and ingestion.status == IngestionStatus.COMPLETED
            and not force
        ):
            return IngestionStatusResponse.model_validate(ingestion)

        # 3  upsert tracking row and publish PROCESSING state.
        #
        # We commit *before* the heavy work so that concurrent callers
        # of GET /rag/ingest/{id}/status observe the in-progress state
        # instead of a stale PENDING/COMPLETED row. This is the only
        # reason we commit twice in this method - the second commit
        # at the end persists the terminal status.
        if not ingestion:
            ingestion = BookIngestion(
                book_id=book_id,
                status=IngestionStatus.PROCESSING,
            )
            self._session.add(ingestion)
        else:
            ingestion.status = IngestionStatus.PROCESSING
            ingestion.error_message = None
            ingestion.updated_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(ingestion)

        try:
            # 4  drop stale chunks on re-ingest.
            #
            # SupabaseVectorStore.add_documents performs INSERTs with
            # newly generated UUIDs - it is *not* an upsert keyed on
            # metadata. Without this delete, a forced re-ingest would
            # duplicate every chunk in the table and corrupt retrieval.
            if force:
                self._vector_store.delete_by_book_id(book_id)

            # 5  load -> chunk -> store
            pages = self._pdf_loader.load(
                book.file_path, book_id, book.title,
            )
            chunks = self._chunker.chunk_documents(pages)
            total_stored = self._vector_store.add_documents(chunks)

            # 6  mark success (single commit for terminal state)
            ingestion.status = IngestionStatus.COMPLETED
            ingestion.total_chunks = total_stored
            ingestion.total_pages = len(pages)
            ingestion.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            self._session.refresh(ingestion)

            logger.info(
                "Ingested book %d: %d chunks from %d pages",
                book_id,
                total_stored,
                len(pages),
            )
            return IngestionStatusResponse.model_validate(ingestion)

        except Exception as exc:
            ingestion.status = IngestionStatus.FAILED
            ingestion.error_message = str(exc)[:500]
            ingestion.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            logger.error("Ingestion failed for book %d: %s", book_id, exc)
            if isinstance(exc, RAGIngestionException):
                raise
            raise RAGIngestionException(f"Ingestion failed: {exc}") from exc

    #  Query 

    async def query(self, request: RAGQueryRequest) -> RAGQueryResponse:
        """
        RAG query pipeline:
        1. Embed the user question
        2. Cosine-similarity search in the vector store
        3. Filter by threshold
        4. Assemble prompt with retrieved context
        5. Send to LLM and return answer + sources
        """
        try:
            # GUARDRAIL (InputGuard): inspect the raw user question before
            # doing any retrieval or LLM work.
            enforce(input_guard.check_user_prompt(request.query, stage="rag_query"))

            # 1  optional book filter
            filter_dict: dict = {}
            if request.book_id is not None:
                ingestion = self._get_ingestion(request.book_id)
                if not ingestion or ingestion.status != IngestionStatus.COMPLETED:
                    raise BookNotIngestedException(
                        f"Book {request.book_id} has not been ingested yet"
                    )
                filter_dict["book_id"] = request.book_id
            request.model = settings.EMBEDDING_MODEL

            # 2  retrieve
            results = self._vector_store.similarity_search(
                query=request.query,
                top_k=request.top_k,
                filter=filter_dict if filter_dict else None,
            )

            # 3  threshold filter
            filtered = [
                (doc, score)
                for doc, score in results
                if score >= request.similarity_threshold
            ]

            if not filtered:
                return RAGQueryResponse(
                    answer=(
                        "I couldn't find relevant information in the "
                        "ingested books to answer your question."
                    ),
                    sources=[],
                    model=request.model or settings.LLM_MODEL,
                    provider=settings.LLM_PROVIDER,
                )

            # 4  build context
            context_parts: list[str] = []
            sources: list[RAGChunkSource] = []

            for doc, score in filtered:
                meta = doc.metadata
                context_parts.append(
                    f"[Book: {meta.get('book_title', 'Unknown')}, "
                    f"Page: {meta.get('page_number', 'N/A')}]\n"
                    f"{doc.page_content}"
                )
                sources.append(
                    RAGChunkSource(
                        content=doc.page_content,
                        book_id=meta.get("book_id", 0),
                        book_title=meta.get("book_title", "Unknown"),
                        page_number=meta.get("page_number"),
                        chunk_index=meta.get("chunk_index", 0),
                        similarity=score,
                    )
                )

            context = "\n\n---\n\n".join(context_parts)

            # GUARDRAIL (DocumentGuard): scan the untrusted PDF/book context
            # for injection attempts BEFORE it ever reaches the model.
            enforce(input_guard.check_document_context(context))

            # 5  LLM call
            system_prompt = RAG_SYSTEM_PROMPT.format(context=context)
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=request.query),
            ]

            llm = build_llm_provider(
                temperature=(
                    request.temperature
                    if request.temperature is not None
                    else 0.3
                ),
                max_tokens=request.max_tokens,
            )
            ai_message = await llm.ainvoke(messages)
            answer = str(ai_message.content)

            # GUARDRAIL (OutputGuard): never return unsafe model output, and
            # make sure the answer is actually usable (summary-quality check).
            enforce(output_guard.check_output(answer))
            enforce(output_guard.check_summary_quality(answer))

            return RAGQueryResponse(
                answer=answer,
                sources=sources,
                model=llm.model_name,
                provider=llm.provider_name,
            )

        except (BookNotIngestedException, RAGQueryException, GuardrailBlockedException):
            raise
        except Exception as exc:
            logger.error("RAG query failed: %s", exc)
            raise RAGQueryException(f"Query failed: {exc}") from exc

    #  Status 

    def get_ingestion_status(self, book_id: int) -> IngestionStatusResponse:
        ingestion = self._get_ingestion(book_id)
        if not ingestion:
            raise BookNotIngestedException(
                f"Book {book_id} has not been ingested"
            )
        return IngestionStatusResponse.model_validate(ingestion)

    #  Private helpers 

    def _get_ingestion(self, book_id: int) -> Optional[BookIngestion]:
        stmt = select(BookIngestion).where(BookIngestion.book_id == book_id)
        return self._session.exec(stmt).first()
