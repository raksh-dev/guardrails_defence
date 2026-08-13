"""
OpenRouter Embeddings

A LangChain-compatible ``Embeddings`` implementation that calls the
OpenRouter REST API directly.

Why not ``OpenAIEmbeddings(base_url="https://openrouter.ai/api/v1")``?
Because LangChain's ``OpenAIEmbeddings`` uses the ``tiktoken`` library to
count tokens before the API call and then validates that the response
contains the expected number of embedding objects.  OpenRouter's embedding
endpoint does not echo token counts back in its response, which causes the
OpenAI SDK to raise ``ValueError: No embedding data received`` even when
the call itself succeeds.
(Upstream bug: https://github.com/langchain-ai/langchain/issues/35204)

This implementation bypasses that token-counting path entirely by using
``httpx`` to call the REST endpoint directly.
"""
import logging
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)

_OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"


class OpenRouterEmbeddings(Embeddings):
    """
    Calls the OpenRouter ``/embeddings`` endpoint and returns raw
    float vectors as a standard LangChain ``Embeddings`` object.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = _OPENROUTER_EMBEDDINGS_URL,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        if not self._base_url.endswith("/embeddings"):
            self._base_url = f"{self._base_url}/embeddings"
        self._timeout = timeout

    #  internal 

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """POST texts to the OpenRouter embeddings endpoint."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self._model, "input": texts}

        response = httpx.post(
            self._base_url,
            headers=headers,
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()

        data = response.json()
        # Sort by index to preserve order (OpenRouter may shuffle)
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    #  Embeddings interface 

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of document strings."""
        logger.debug("OpenRouterEmbeddings.embed_documents: %d texts", len(texts))
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        logger.debug("OpenRouterEmbeddings.embed_query")
        return self._embed([text])[0]
