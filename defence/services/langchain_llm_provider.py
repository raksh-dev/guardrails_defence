import logging
from pydantic import SecretStr
from typing import AsyncIterator, NoReturn
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from core.config import settings
from core.exceptions import (
    LLMConfigurationException,
    LLMProviderException,
    LLMRateLimitException,
    LLMTimeoutException,
    UnsupportedLLMProviderException,
)
from schemas.chat import ChatMessage

logger = logging.getLogger(__name__)

class LangChainLLMProvider:
    """
    Thin wrapper around a LangChain BaseChatModel.
    """

    def __init__(self, chat_model: BaseChatModel, provider: str):
        self._model = chat_model
        self._provider = provider

    @property
    def chat_model(self) -> BaseChatModel:
        return self._model

    @property
    def model_name(self) -> str:
        # Different LangChain chat models expose the id under different
        # attributes: ChatOpenAI uses ``model_name``; ChatOllama,
        # ChatGoogleGenerativeAI and ChatAnthropic use ``model``.
        return str(
            getattr(self._model, "model_name", None)
            or getattr(self._model, "model", None)
            or "unknown"
        )

    @property
    def provider_name(self) -> str:
        return self._provider

    def invoke(self, messages: list[ChatMessage]) -> AIMessage:
        lc_msgs = _to_langchain_messages(messages)
        try:
            return self._model.invoke(lc_msgs)
        except Exception as exc:
            _raise_normalised(exc)
            

    async def ainvoke(self, messages: list[ChatMessage]) -> AIMessage:
        lc_msgs = _to_langchain_messages(messages)
        try:
            return await self._model.ainvoke(lc_msgs)
        except Exception as exc:
            _raise_normalised(exc)
            

    async def astream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        lc_msgs = _to_langchain_messages(messages)
        try:
            async for chunk in self._model.astream(lc_msgs):
                if chunk.content:
                    yield str(chunk.content)
        except Exception as exc:
            _raise_normalised(exc)

# Providers that speak the OpenAI Chat Completions API. Any endpoint that is
# OpenAI-compatible works through this single branch — you only change
# LLM_BASE_URL + LLM_MODEL + LLM_API_KEY. This covers most free options
# (OpenRouter free models, Groq) and paid ones (OpenAI) alike.
_OPENAI_COMPATIBLE = {
    "openai", "openrouter", "groq", "together", "deepseek",
    "openai_compatible", "custom",
}

# Default OpenAI-compatible base URLs by provider alias, used when LLM_BASE_URL
# is left at its (OpenRouter) default. Lets you switch provider with one line.
_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

_OPENROUTER_DEFAULT = "https://openrouter.ai/api/v1"


def build_llm_provider(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    api_key: str | None = None,
) -> LangChainLLMProvider:
    """
    Factory that returns a configured LangChainLLMProvider for ANY supported
    backend. Falls back to ``settings.*`` for every parameter not supplied.

    Supported ``provider`` values:

    * OpenAI-compatible (one code path): ``openrouter`` (default), ``openai``,
      ``groq``, ``together``, ``deepseek``, or ``custom``/``openai_compatible``
      for any other OpenAI-style endpoint. Set ``LLM_BASE_URL`` to point at it.
    * ``ollama``  - local models, **no API key required** (free, private).
    * ``google``  - Google Gemini (free tier available).
    * ``anthropic`` - Claude (paid).

    To go from a free model to a paid one later you only change ``.env`` -
    no code changes.
    """
    provider_name = (provider or settings.LLM_PROVIDER).lower().strip()
    model_name = model or settings.LLM_MODEL
    temperature_val = temperature if temperature is not None else settings.LLM_TEMPERATURE
    max_tokens_val = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
    api_key_val = api_key or settings.LLM_API_KEY

    chat_model: BaseChatModel

    # --- 1. OpenAI-compatible endpoints (OpenRouter/OpenAI/Groq/...) ---------
    if provider_name in _OPENAI_COMPATIBLE:
        if not api_key_val:
            raise LLMConfigurationException(
                f"No API key configured for provider '{provider_name}'. "
                "Set LLM_API_KEY in .env or pass it in the request."
            )
        from langchain_openai import ChatOpenAI

        # Pick the endpoint: explicit LLM_BASE_URL wins; otherwise use the
        # provider's known default. If a non-OpenRouter provider was chosen
        # but LLM_BASE_URL is still the OpenRouter default, fall back to that
        # provider's default so switching providers is a one-line change.
        base_url = settings.LLM_BASE_URL
        if not base_url or (
            provider_name != "openrouter" and base_url == _OPENROUTER_DEFAULT
        ):
            base_url = _DEFAULT_BASE_URLS.get(provider_name)

        chat_model = ChatOpenAI(
            model=model_name,
            api_key=SecretStr(api_key_val),
            base_url=base_url,
            temperature=temperature_val,
            max_completion_tokens=max_tokens_val,
            max_retries=settings.LLM_MAX_RETRIES,
            timeout=settings.LLM_REQUEST_TIMEOUT,
        )
        return LangChainLLMProvider(chat_model, provider_name)

    # --- 2. Ollama (local, free, no key) ------------------------------------
    if provider_name == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise LLMConfigurationException(
                "langchain-ollama is not installed. Add 'langchain-ollama' "
                "to requirements.txt to use local Ollama models."
            ) from exc
        chat_model = ChatOllama(
            model=model_name,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature_val,
            num_predict=max_tokens_val,
        )
        return LangChainLLMProvider(chat_model, provider_name)

    # --- 3. Google Gemini (free tier available) -----------------------------
    if provider_name in ("google", "gemini", "google_genai"):
        if not api_key_val:
            raise LLMConfigurationException(
                "No API key configured for Google. Set LLM_API_KEY to your "
                "Google AI Studio key (https://aistudio.google.com/apikey)."
            )
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise LLMConfigurationException(
                "langchain-google-genai is not installed."
            ) from exc
        chat_model = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key_val,
            temperature=temperature_val,
            max_output_tokens=max_tokens_val,
        )
        return LangChainLLMProvider(chat_model, "google")

    # --- 4. Anthropic / Claude (paid) ---------------------------------------
    if provider_name in ("anthropic", "claude"):
        if not api_key_val:
            raise LLMConfigurationException(
                "No API key configured for Anthropic. Set LLM_API_KEY."
            )
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise LLMConfigurationException(
                "langchain-anthropic is not installed."
            ) from exc
        chat_model = ChatAnthropic(
            model=model_name,
            api_key=SecretStr(api_key_val),
            temperature=temperature_val,
            max_tokens=max_tokens_val,
            timeout=settings.LLM_REQUEST_TIMEOUT,
            max_retries=settings.LLM_MAX_RETRIES,
        )
        return LangChainLLMProvider(chat_model, "anthropic")

    raise UnsupportedLLMProviderException(
        f"Provider '{provider_name}' is not supported. Choose from: "
        "openrouter, openai, groq, together, deepseek, ollama, google, "
        "anthropic — or any OpenAI-compatible endpoint via provider=custom "
        "+ LLM_BASE_URL."
    )

def _to_langchain_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    """Convert our schema messages to LangChain message objects."""
    mapping = {
        "system": SystemMessage,
        "user": HumanMessage,
        "assistant": AIMessage,
    }
    return [mapping[m.role](content=m.content) for m in messages]

def _raise_normalised(exc: Exception) -> NoReturn:
    """Map provider SDK errors to our exception hierarchy."""
    msg = str(exc).lower()
    logger.error("LLM provider error: %s", exc)

    if "rate" in msg or "429" in msg or "quota" in msg:
        raise LLMRateLimitException(str(exc))
    if "timeout" in msg or "timed out" in msg:
        raise LLMTimeoutException(str(exc))
    raise LLMProviderException(str(exc))