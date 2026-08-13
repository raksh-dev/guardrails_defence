"""
Supabase pgvector Vector Store

Concrete :class:`~services.rag.protocols.VectorStore` implementation
backed by Supabase pgvector through LangChain's ``SupabaseVectorStore``.
"""
import json
import logging
import time
from typing import Optional

from langchain_core.documents import Document
from langchain_community.vectorstores import SupabaseVectorStore
from supabase import Client, create_client

from core.config import settings
from core.exceptions import RAGIngestionException, RAGQueryException
from services.rag.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


def _build_postgrest_client() -> Client:
    """
    Build a Supabase client pointed at the project base URL so that
    ``client.table()`` resolves to PostgREST (``/rest/v1/``) instead
    of the Storage API.

    If ``SUPABASE_URL`` is explicitly set in .env, that value is used.
    Otherwise the base URL is derived from ``STORAGE_URL`` by removing
    the ``.storage`` subdomain segment
    (e.g. ``https://xyz.storage.supabase.co`` -> ``https://xyz.supabase.co``).
    The key used is ``SUPABASE_SERVICE_KEY`` when set, falling back to
    ``STORAGE_ACCOUNT_SECRET``.
    """
    url = settings.SUPABASE_URL or settings.STORAGE_URL.replace(
        ".storage.supabase.co", ".supabase.co"
    )
    key = settings.SUPABASE_SERVICE_KEY or settings.STORAGE_ACCOUNT_SECRET
    logger.info("Vector store PostgREST client URL: %s", url)
    return create_client(url, key)


class SupabaseVectorStoreService:
    """
    Implements :class:`services.rag.protocols.VectorStore` against
    Supabase pgvector.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        client: Client | None = None,
    ) -> None:
        self._client: Client = client or _build_postgrest_client()
        self._embedding_service = embedding_service
        self._table_name = settings.VECTOR_TABLE_NAME
        self._query_function = settings.VECTOR_QUERY_FUNCTION
        # Cache: SupabaseVectorStore is a thin stateless wrapper but
        # constructing it allocates LangChain runtime objects, so we
        # keep a single instance per service.
        self._store: SupabaseVectorStore | None = None

    # helpers 

    def _get_store(self) -> SupabaseVectorStore:
        if self._store is None:
            self._store = SupabaseVectorStore(
                client=self._client,
                embedding=self._embedding_service.embeddings,
                table_name=self._table_name,
                query_name=self._query_function,
            )
        return self._store

    # write

    def add_documents(
        self,
        documents: list[Document],
        batch_size: int = 20,
        max_retries: int = 4,
    ) -> int:
        """
        Embed and insert *documents* into the vector store in batches.

        Batches are kept small (default 20) and each batch is retried with
        exponential backoff, because the Supabase PostgREST connection can be
        reset mid-upload (WinError 10054 / httpx.ReadError) on flaky networks
        or when the request body is large.

        NOTE: ``SupabaseVectorStore.add_documents`` performs INSERTs with
        freshly generated UUIDs - it does *not* upsert by metadata. That
        is why callers must explicitly :meth:`delete_by_book_id` before
        re-ingesting an existing book; otherwise old chunks remain in
        place alongside the new ones and pollute retrieval results.
        """
        store = self._get_store()
        total_added = 0
        total_batches = (len(documents) + batch_size - 1) // batch_size

        try:
            for i in range(0, len(documents), batch_size):
                batch = documents[i : i + batch_size]
                self._add_batch_with_retry(store, batch, max_retries)
                total_added += len(batch)
                logger.info(
                    "Stored batch %d/%d: %d / %d chunks",
                    i // batch_size + 1,
                    total_batches,
                    total_added,
                    len(documents),
                )
            return total_added
        except Exception as exc:
            logger.exception("Vector store insert failed")
            raise RAGIngestionException(
                f"Failed to store embeddings: {exc}"
            ) from exc

    def _add_batch_with_retry(self, store, batch, max_retries: int) -> None:
        """Insert one batch, retrying transient network errors with backoff."""
        for attempt in range(1, max_retries + 1):
            try:
                store.add_documents(batch)
                return
            except Exception as exc:  # noqa: BLE001 - postgrest/httpx raise many types
                if attempt >= max_retries:
                    raise
                wait = 2 ** (attempt - 1)  # 1s, 2s, 4s, ...
                logger.warning(
                    "Vector insert batch failed (attempt %d/%d): %s — retrying in %ds",
                    attempt, max_retries, exc, wait,
                )
                time.sleep(wait)

    # sread 
    def similarity_search(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[dict] = None,
    ) -> list[tuple[Document, float]]:
        """
        Embed *query* and return the *top_k* most similar chunks
        together with their cosine-similarity scores.

        Uses a direct Supabase RPC call instead of LangChain's
        ``similarity_search_with_relevance_scores`` to avoid an
        incompatibility with supabase-py v2 (``SyncRPCFilterRequestBuilder``
        no longer exposes ``.params``).
        """
        try:
            query_embedding = self._embedding_service.embeddings.embed_query(query)
            rpc_params: dict = {
                "query_embedding": query_embedding,
                "match_count": top_k,
            }
            if filter:
                rpc_params["filter"] = filter

            response = self._client.rpc(self._query_function, rpc_params).execute()

            results: list[tuple[Document, float]] = []
            for row in response.data or []:
                doc = Document(
                    page_content=row["content"],
                    metadata=row.get("metadata") or {},
                )
                score: float = float(row.get("similarity", 0.0))
                results.append((doc, score))
            return results
        except Exception as exc:
            logger.exception("Vector similarity search failed")
            raise RAGQueryException(
                f"Vector store query failed: {exc}"
            ) from exc

    # delete

    def delete_by_book_id(self, book_id: int) -> None:
        """Remove every chunk that belongs to *book_id*."""
        try:
            self._client.table(self._table_name).delete().filter(
                "metadata", "cs", json.dumps({"book_id": book_id}),
            ).execute()
            logger.info("Deleted all chunks for book %d", book_id)
        except Exception as exc:
            logger.exception("Vector store delete failed")
            raise RAGIngestionException(
                f"Failed to delete chunks for book {book_id}: {exc}"
            ) from exc
