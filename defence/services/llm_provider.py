from typing import AsyncIterator, Protocol
from langchain_core.messages import AIMessage
from schemas.chat import ChatMessage

class LLMProvider(Protocol):
    """
    Interface for LLM Services
    """

    @property
    def model_name(self) -> str: ...

    @property
    def provider_name(self) -> str: ...

    def invoke(self, messages: list[ChatMessage]) -> AIMessage: ...

    async def ainvoke(self, messages: list[ChatMessage]) -> AIMessage: ...

    async def astream(self, messages: list[ChatMessage]) -> AsyncIterator[str]: ...
