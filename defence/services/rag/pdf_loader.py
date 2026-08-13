"""
PDF Loader Service

Downloads a book's PDF from object storage and extracts text page-by-page
using PyPDF. Each page becomes a LangChain Document with rich metadata
that travels through the rest of the RAG pipeline.
"""
import io
import logging

from langchain_core.documents import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from core.exceptions import BookFileNotFoundException, RAGIngestionException
from services.storage import StorageService

logger = logging.getLogger(__name__)


class PDFLoaderService:
    """Download a PDF from object storage and return per-page Documents."""

    def __init__(self, storage: StorageService):
        self._storage = storage

    def load(
        self,
        storage_path: str,
        book_id: int,
        book_title: str,
    ) -> list[Document]:
        """
        Download the PDF identified by *storage_path* and return one
        ``Document`` per page that contains extractable text.
        """
        logger.info("Downloading PDF for book %d from %s", book_id, storage_path)

        #  download 
        try:
            pdf_bytes: bytes = self._storage.download(storage_path)
        except BookFileNotFoundException:
            raise
        except Exception as exc:
            logger.exception("PDF download failed for book %d", book_id)
            raise RAGIngestionException(
                f"Failed to download PDF for book {book_id}: {exc}"
            ) from exc

        #  parse 
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
        except PdfReadError as exc:
            logger.exception("PDF parse failed for book %d", book_id)
            raise RAGIngestionException(
                f"Could not parse PDF for book {book_id}: {exc}"
            ) from exc

        total_pages = len(reader.pages)
        documents: list[Document] = []

        # convert into List[Document] from bytes
        for page_num, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:  # noqa: BLE001 - pypdf raises many types
                logger.warning(
                    "Failed to extract text on page %d of book %d: %s",
                    page_num, book_id, exc,
                )
                continue

            if not text:
                logger.debug("Page %d of book %d is empty, skipping", page_num, book_id)
                continue

            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "book_id": book_id,
                        "book_title": book_title,
                        "page_number": page_num,
                        "total_pages": total_pages,
                        "source": storage_path,
                    },
                )
            )

        if not documents:
            raise RAGIngestionException(
                f"No extractable text found in PDF for book {book_id}"
            )

        logger.info(
            "Extracted %d non-empty pages out of %d for book %d",
            len(documents),
            total_pages,
            book_id,
        )
        return documents
