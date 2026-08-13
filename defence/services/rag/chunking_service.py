"""
Chunking Service

Splits per-page Documents into smaller, overlapping chunks.

Splitter selection is pluggable:
* Pass any LangChain ``TextSplitter`` instance to the constructor, or
* leave it ``None`` and let :func:`_build_splitter` pick one based on
  ``settings.RAG_SPLITTER_TYPE`` (``recursive`` | ``character`` | ``token``).

This keeps the orchestration layer (``RAGService``) decoupled from the
specific splitting strategy.
"""
import logging

from langchain_core.documents import Document
from langchain_text_splitters import (
    CharacterTextSplitter,
    RecursiveCharacterTextSplitter,
    TextSplitter,
    TokenTextSplitter,
)

from core.config import settings

logger = logging.getLogger(__name__)


class ChunkingService:
    """Stateless chunker - one instance can be shared across requests."""

    def __init__(
        self,
        splitter: TextSplitter | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self._chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self._chunk_overlap = chunk_overlap or settings.RAG_CHUNK_OVERLAP
        self._splitter: TextSplitter = splitter or self._build_splitter()

    #  factory -

    def _build_splitter(self) -> TextSplitter:
        kind = (settings.RAG_SPLITTER_TYPE or "recursive").lower()

        if kind == "recursive":
            return RecursiveCharacterTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
                separators=["\n\n", "\n", ". ", ", ", " ", ""],
                length_function=len,
                is_separator_regex=False,
            )
        if kind == "character":
            return CharacterTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
        if kind == "token":
            return TokenTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )

        raise ValueError(f"Unsupported RAG_SPLITTER_TYPE: {kind!r}")

    #  public 

    def chunk_documents(self, documents: list[Document]) -> list[Document]:
        """
        Split *documents* (typically one per page) into smaller chunks.

        Returns a flat list where every chunk carries the original
        page-level metadata extended with ``chunk_index`` and
        ``chunk_size``.
        """
        try:
            all_chunks: list[Document] = []
            global_index = 0

            for doc in documents:
                page_chunks = self._splitter.split_documents([doc])
                for chunk in page_chunks:
                    chunk.metadata["chunk_index"] = global_index
                    chunk.metadata["chunk_size"] = len(chunk.page_content)
                    global_index += 1
                    all_chunks.append(chunk)

            logger.info(
                "Split %d pages into %d chunks (size=%d, overlap=%d)",
                len(documents),
                len(all_chunks),
                self._chunk_size,
                self._chunk_overlap,
            )
            return all_chunks
        except Exception as exc:
            logger.exception("Chunking failed")
            raise RuntimeError(f"Failed to chunk documents: {exc}") from exc
