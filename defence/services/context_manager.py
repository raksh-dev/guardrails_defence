import logging
from typing import Optional
from sqlmodel import Session
from schemas.chat import ChatMessage, ChatRequest
from models.conversation import Message
from services.conversation_service import ConversationService
from services.langchain_llm_provider import build_llm_provider
from core.config import settings

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Manages conversation context with two compression strategies:
    1. Sliding Window: Keep only the last N messages
    2. Summarization: Periodically summarize old messages
    """

    def __init__(self, session: Session):
        self.session = session
        self.conv_service = ConversationService(session)

    def build_context(
        self,
        conversation_id: int,
        include_system_prompt: bool = True,
    ) -> list[ChatMessage]:
        """
        Build context for LLM using sliding window + summarization.

        Strategy:
        1. Check if we have a summary
        2. Get recent messages (sliding window)
        3. Combine summary + recent messages
        """
        messages = self.conv_service.get_messages(conversation_id)
        total_count = len(messages)

        if total_count == 0:
            return []

        context: list[ChatMessage] = []

        if include_system_prompt:
            system_msg = self._get_system_message(messages)
            if system_msg:
                context.append(system_msg)

        summary = self.conv_service.get_latest_summary(conversation_id)

        if summary:
            context.append(
                ChatMessage(
                    role="system",
                    content=f"Previous conversation summary: {summary.summary_content}",
                )
            )

            messages_after_summary = [
                m for m in messages if m.id > summary.messages_summarized
            ]
            recent_messages = messages_after_summary[
                -settings.CONTEXT_WINDOW_SIZE :
            ]
        else:
            recent_messages = messages[-settings.CONTEXT_WINDOW_SIZE :]

        for msg in recent_messages:
            context.append(ChatMessage(role=msg.role, content=msg.content))

        logger.info(
            f"Built context: {len(context)} messages "
            f"(total in DB: {total_count}, has_summary: {summary is not None})"
        )

        return context

    def should_summarize(self, conversation_id: int) -> bool:
        """
        Check if we should create a summary.
        Summarize every SUMMARIZATION_THRESHOLD messages.
        """
        total_messages = self.conv_service.count_messages(conversation_id)
        latest_summary = self.conv_service.get_latest_summary(conversation_id)

        if total_messages < settings.SUMMARIZATION_THRESHOLD:
            return False

        if not latest_summary:
            return True

        messages_since_summary = total_messages - latest_summary.messages_summarized
        return messages_since_summary >= settings.SUMMARIZATION_THRESHOLD

    async def create_summary(
        self, conversation_id: int, model: Optional[str] = None
    ) -> None:
        """
        Create a summary of old messages using an LLM.
        """
        latest_summary = self.conv_service.get_latest_summary(conversation_id)

        if latest_summary:
            messages = self.conv_service.get_messages(conversation_id)
            messages_to_summarize = [
                m for m in messages if m.id > latest_summary.messages_summarized
            ][: -settings.CONTEXT_WINDOW_SIZE]
        else:
            all_messages = self.conv_service.get_messages(conversation_id)
            messages_to_summarize = all_messages[: -settings.CONTEXT_WINDOW_SIZE]

        if len(messages_to_summarize) < 5:
            logger.info("Not enough messages to summarize, skipping")
            return

        conversation_text = "\n".join(
            [f"{m.role}: {m.content}" for m in messages_to_summarize]
        )

        summary_prompt = [
            ChatMessage(
                role="system",
                content=(
                    "You are a conversation summarizer. "
                    "Summarize the following conversation concisely, "
                    "preserving key facts, decisions, and context. "
                    "Keep the summary under 200 words."
                ),
            ),
            ChatMessage(role="user", content=conversation_text),
        ]

        llm = build_llm_provider(
            model=model or settings.SUMMARY_MODEL,
            temperature=0.3,
            max_tokens=300,
        )

        try:
            response = await llm.ainvoke(summary_prompt)
            summary_content = str(response.content)

            last_summarized_id = messages_to_summarize[-1].id

            self.conv_service.create_summary(
                conversation_id=conversation_id,
                summary_content=summary_content,
                messages_summarized=last_summarized_id,
                model_used=model or settings.SUMMARY_MODEL,
            )

            logger.info(
                f"Created summary for conversation {conversation_id}, "
                f"summarized {len(messages_to_summarize)} messages"
            )

        except Exception as e:
            logger.error(f"Failed to create summary: {e}")

    def _get_system_message(self, messages: list[Message]) -> Optional[ChatMessage]:
        """Extract the first system message if it exists."""
        for msg in messages:
            if msg.role == "system":
                return ChatMessage(role="system", content=msg.content)
        return None
