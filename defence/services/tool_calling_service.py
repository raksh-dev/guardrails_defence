"""
Service for handling LLM function calling with tools.
Integrates tool execution with conversation flow.
"""
import json
import logging
from typing import Optional
from sqlmodel import Session
from langchain_core.messages import AIMessage, ToolMessage

from schemas.chat import ChatMessage
from services.guardrails import enforce, input_guard, output_guard, tool_guard
from services.tools.tool_definitions import LIBRARY_TOOLS, validate_tool_definitions
from services.tools.tool_executor import ToolExecutor
from services.storage import StorageService
from services.langchain_llm_provider import LangChainLLMProvider, _to_langchain_messages

logger = logging.getLogger(__name__)


class ToolCallingService:
    """Handles LLM interactions with function calling enabled."""

    def __init__(
        self,
        session: Session,
        storage: StorageService,
        llm_provider: LangChainLLMProvider,
        enabled_tools: Optional[list[str]] = None,
    ):
        self.session = session
        self.storage = storage
        self.llm_provider = llm_provider
        self.tool_executor = ToolExecutor(session, storage)
        self.enabled_tools = enabled_tools or []

        # Validate that tool definitions match executor registry
        validate_tool_definitions(self.tool_executor.get_available_tools())

        # Validate enabled_tools exist in executor
        if self.enabled_tools:
            available = set(self.tool_executor.get_available_tools())
            invalid = set(self.enabled_tools) - available
            if invalid:
                raise ValueError(f"Invalid tools requested: {invalid}. Available: {available}")

    def get_available_tools(self) -> list[dict]:
        """Filter tools based on enabled_tools list."""
        if not self.enabled_tools:
            return []

        return [
            tool
            for tool in LIBRARY_TOOLS
            if tool["function"]["name"] in self.enabled_tools
        ]

    async def complete_with_tools(
        self,
        messages: list[ChatMessage],
    ) -> tuple[str, Optional[list[dict]]]:
        """
        Complete a chat request with tool calling enabled.

        Returns:
            tuple: (response_content, tool_calls_metadata)
        """
        # GUARDRAIL (InputGuard + ConversationHistoryGuard): inspect the full
        # context — current message AND earlier turns — before the model runs.
        # This blocks distributed/multi-turn injection and stops a poisoned
        # context from ever reaching the LLM or triggering tool calls.
        enforce(input_guard.check_messages(messages))

        available_tools = self.get_available_tools()

        if not available_tools:
            logger.warning("Tool calling requested but no tools are enabled")
            return await self._complete_without_tools(messages)

        # Bind tools to the underlying LangChain model
        llm_with_tools = self.llm_provider.chat_model.bind_tools(available_tools)

        # Convert to LangChain messages
        lc_messages = _to_langchain_messages(messages)

        # Initial LLM call
        ai_message: AIMessage = await llm_with_tools.ainvoke(lc_messages)

        # Check if LLM wants to call tools
        if not ai_message.tool_calls:
            # No tools called, return response directly
            content = str(ai_message.content)
            enforce(output_guard.check_output(content))
            return content, None

        # GUARDRAIL (ToolCallGuard): defense-in-depth before executing any
        # tool. Refuses mutating tools (create_loan/extend_loan) if the
        # conversation context shows injection indicators.
        enforce(tool_guard.check_tool_calls(ai_message.tool_calls, messages=messages))

        # Execute tool calls
        tool_call_metadata = []
        lc_messages.append(ai_message)

        for tool_call in ai_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]

            logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

            # Execute the tool
            result_json = self.tool_executor.execute(tool_name, tool_args)

            # Store metadata for response
            tool_call_metadata.append({
                "tool": tool_name,
                "arguments": tool_args,
                "result": json.loads(result_json),
            })

            # Add tool result to conversation
            tool_message = ToolMessage(
                content=result_json,
                tool_call_id=tool_call_id,
            )
            lc_messages.append(tool_message)

        # Second LLM call with tool results
        final_response: AIMessage = await llm_with_tools.ainvoke(lc_messages)

        # GUARDRAIL (OutputGuard): block unsafe output before returning.
        final_content = str(final_response.content)
        enforce(output_guard.check_output(final_content))

        return final_content, tool_call_metadata

    async def _complete_without_tools(
        self,
        messages: list[ChatMessage],
    ) -> tuple[str, None]:
        """Fallback to regular completion without tools."""
        ai_message = await self.llm_provider.ainvoke(messages)
        return str(ai_message.content), None
