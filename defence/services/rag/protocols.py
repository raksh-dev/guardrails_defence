"""
RAG Protocols

Backend-agnostic interfaces so RAG orchestration code does not depend on
any specific vector DB / embedding / splitter implementation.
"""
from typing import Optional, Protocol, runtime_checkable

from langchain_core.documents import Document


@runtime_checkable
class VectorStore(Protocol):
    """Minimum surface every vector backend must implement."""

    def add_documents(
        self,
        documents: list[Document],
        batch_size: int = 100,
    ) -> int:
        """Embed and persist *documents*. Returns number stored."""
        ...

    def similarity_search(
        self,
        query: str,
        top_k: int = 5,
        filter: Optional[dict] = None,
    ) -> list[tuple[Document, float]]:
        """Return *top_k* (document, score) pairs ranked by relevance."""
        ...

    def delete_by_book_id(self, book_id: int) -> None:
        """Remove every chunk associated with *book_id*."""
        ...
