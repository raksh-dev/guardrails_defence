"""
Chat service — orchestrates conversations between users and the LLM.

Guardrails are applied here so that BOTH the stateless ``/chat`` endpoint and
the conversation chat path (which calls ``acomplete``) are protected without
adding any logic to the routers:

* InputGuard / ConversationHistoryGuard run on the message list before the LLM.
* OutputGuard runs on the model response before it is returned.
"""
import json
import logging
import uuid
from typing import AsyncIterator

from core.config import settings
from schemas.chat import ChatMessage, ChatRequest, ChatResponse, TokenUsage
from services.guardrails import enforce, input_guard, output_guard
from services.langchain_llm_provider import LangChainLLMProvider, build_llm_provider

logger = logging.getLogger(__name__)


class ChatService:
    """Thin orchestrator that delegates to an LLMProvider."""

    def __init__(self, provider: LangChainLLMProvider):
        self._provider = provider

    def complete(self, request: ChatRequest) -> ChatResponse:
        enforce(input_guard.check_messages(request.messages))

        ai_message = self._provider.invoke(request.messages)
        content = str(ai_message.content)
        enforce(output_guard.check_output(content))

        usage = _extract_usage(ai_message)
        return ChatResponse(
            id=_make_id(),
            model=self._provider.model_name,
            provider=self._provider.provider_name,
            message=ChatMessage(role="assistant", content=content),
            usage=usage,
        )

    async def acomplete(self, request: ChatRequest) -> ChatResponse:
        # GUARDRAIL: scan the full message history (current prompt + earlier
        # turns) before calling the model.
        enforce(input_guard.check_messages(request.messages))

        ai_message = await self._provider.ainvoke(request.messages)
        content = str(ai_message.content)

        # GUARDRAIL: block unsafe model output before returning it.
        enforce(output_guard.check_output(content))

        usage = _extract_usage(ai_message)
        return ChatResponse(
            id=_make_id(),
            model=self._provider.model_name,
            provider=self._provider.provider_name,
            message=ChatMessage(role="assistant", content=content),
            usage=usage,
        )

    async def astream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Yields text chunks as they arrive from the LLM.
        Each chunk is formatted as a Server-Sent Event.

        The InputGuard runs before streaming begins. If it blocks, a single
        guardrail SSE frame is emitted instead of model output (raising
        mid-stream would corrupt the response). OutputGuard is not applied to
        the streaming endpoint — see GUARDRAILS.md "Limitations".
        """
        guard = input_guard.check_messages(request.messages)
        if guard.blocked:
            body = guard.to_response(settings.GUARDRAILS_DEBUG)
            yield f"data: {json.dumps(body)}\n\n"
            yield "data: [DONE]\n\n"
            return

        async for token in self._provider.astream(request.messages):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

def _make_id() -> str:
    return f"chat-{uuid.uuid4().hex[:12]}"


def _extract_usage(ai_message) -> TokenUsage | None:
    """Try to pull token counts from the LangChain response metadata."""
    meta = getattr(ai_message, "response_metadata", {}) or {}
    usage_data = meta.get("token_usage") or meta.get("usage") or {}
    if not usage_data:
        return None
    return TokenUsage(
        prompt_tokens=usage_data.get("prompt_tokens") or usage_data.get("input_tokens"),
        completion_tokens=usage_data.get("completion_tokens") or usage_data.get("output_tokens"),
        total_tokens=usage_data.get("total_tokens"),
    )

def build_chat_service(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatService:
    llm = build_llm_provider(
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return ChatService(llm)
