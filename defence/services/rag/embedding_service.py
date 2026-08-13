"""
Embedding Service

Backend-agnostic factory around any LangChain ``Embeddings`` implementation.

The concrete provider is selected via ``settings.EMBEDDING_PROVIDER``.

Supported values

* ``openai``       - OpenAI (or any OpenAI-compatible) endpoint via
                     ``langchain_openai.OpenAIEmbeddings``.
* ``openrouter``   - OpenRouter REST API via a custom implementation
                     (``OpenRouterEmbeddings``) that bypasses the broken
                     token-counting path in ``OpenAIEmbeddings``.
                     See ``services/rag/openrouter_embeddings.py``.
* ``ollama``       - Local Ollama server via
                     ``langchain_ollama.OllamaEmbeddings``.

Adding a new provider requires only a new branch in
:meth:`_build_embeddings`. The rest of the RAG pipeline talks to the
abstract ``Embeddings`` interface and is unaffected.
"""
import logging

from pydantic import SecretStr
from langchain_core.embeddings import Embeddings

from core.config import settings
from core.exceptions import EmbeddingConfigurationException

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Thin, reusable wrapper around the configured embedding model."""

    def __init__(
        self,
        embeddings: Embeddings | None = None,
    ) -> None:
        self._embeddings: Embeddings = embeddings or self._build_embeddings()
        logger.info(
            "EmbeddingService initialised  provider=%s  model=%s",
            settings.EMBEDDING_PROVIDER,
            settings.EMBEDDING_MODEL,
        )

    # factory

    @staticmethod
    def _build_embeddings() -> Embeddings:
        provider = (settings.EMBEDDING_PROVIDER or "openai").lower()
        api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY

        # OpenAI (or any OpenAI-compatible endpoint)
        if provider == "openai":
            if not api_key:
                raise EmbeddingConfigurationException(
                    "No embedding API key configured. "
                    "Set EMBEDDING_API_KEY or LLM_API_KEY in .env"
                )
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(
                model=settings.EMBEDDING_MODEL,
                api_key=SecretStr(api_key),
                base_url=settings.EMBEDDING_BASE_URL,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )

        # OpenRouter 
        # OpenRouter exposes an /embeddings endpoint but the token-count
        # validation inside OpenAIEmbeddings fails against it.
        # We use a thin httpx-based implementation that calls the REST
        # endpoint directly instead.
        if provider == "openrouter":
            if not api_key:
                raise EmbeddingConfigurationException(
                    "No embedding API key configured for OpenRouter. "
                    "Set EMBEDDING_API_KEY or LLM_API_KEY in .env"
                )
            from services.rag.openrouter_embeddings import OpenRouterEmbeddings
            return OpenRouterEmbeddings(
                model=settings.EMBEDDING_MODEL,
                api_key=api_key,
                base_url=settings.EMBEDDING_BASE_URL,
            )

        # Ollama (local, free — no API key)
        if provider == "ollama":
            try:
                from langchain_ollama import OllamaEmbeddings
            except ImportError as exc:
                raise EmbeddingConfigurationException(
                    "langchain-ollama is not installed. "
                    "Add it to requirements.txt: langchain-ollama>=0.2.0"
                ) from exc
            return OllamaEmbeddings(
                model=settings.EMBEDDING_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
            )

        # Google Gemini embeddings (free tier)
        # NOTE: Gemini embedding models output fewer dimensions than OpenAI.
        # gemini-embedding-001 defaults to 3072 dims (too large for pgvector's
        # 2000-dim HNSW index), so we explicitly request EMBEDDING_DIMENSIONS
        # (use 768) via output_dimensionality. The pgvector column must match
        # (vector(768)) — see sql/rag_setup_768.sql.
        if provider in ("google", "gemini", "google_genai"):
            if not api_key:
                raise EmbeddingConfigurationException(
                    "No embedding API key configured for Google. "
                    "Set EMBEDDING_API_KEY (or LLM_API_KEY) to a Google AI Studio key."
                )
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
            except ImportError as exc:
                raise EmbeddingConfigurationException(
                    "langchain-google-genai is not installed."
                ) from exc
            return GoogleGenerativeAIEmbeddings(
                model=settings.EMBEDDING_MODEL,
                google_api_key=api_key,
                output_dimensionality=settings.EMBEDDING_DIMENSIONS,
            )

        raise EmbeddingConfigurationException(
            f"Unsupported EMBEDDING_PROVIDER: {provider!r}. "
            "Valid values: openai, openrouter, ollama, google"
        )

    # public helpers

    @property
    def embeddings(self) -> Embeddings:
        """Return the underlying LangChain Embeddings instance."""
        return self._embeddings

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        return self._embeddings.embed_query(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document texts."""
        return self._embeddings.embed_documents(texts)
