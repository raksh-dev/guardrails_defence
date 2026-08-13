from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship, Column, JSON


class Conversation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    member_id: int = Field(foreign_key="member.id", index=True)
    title: str = Field(max_length=255)
    conversation_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    messages: list["Message"] = Relationship(back_populates="conversation")
    
    @property
    def enabled_tools(self) -> Optional[list[str]]:
        """Get enabled_tools from conversation_metadata."""
        if self.conversation_metadata:
            return self.conversation_metadata.get("enabled_tools")
        return None
    
    def set_enabled_tools(self, tools: Optional[list[str]]) -> None:
        """Set enabled_tools in conversation_metadata."""
        if self.conversation_metadata is None:
            self.conversation_metadata = {}
        if tools is not None:
            self.conversation_metadata["enabled_tools"] = tools
        elif "enabled_tools" in self.conversation_metadata:
            del self.conversation_metadata["enabled_tools"]


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str = Field(max_length=20)
    content: str
    model_used: Optional[str] = Field(default=None, max_length=100)
    provider_used: Optional[str] = Field(default=None, max_length=50)
    token_usage: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    message_metadata: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    conversation: Optional[Conversation] = Relationship(back_populates="messages")
    
    @property
    def tool_calls(self) -> Optional[list[dict]]:
        """Get tool_calls from message_metadata."""
        if self.message_metadata:
            return self.message_metadata.get("tool_calls")
        return None
    
    def set_tool_calls(self, calls: Optional[list[dict]]) -> None:
        """Set tool_calls in message_metadata."""
        if self.message_metadata is None:
            self.message_metadata = {}
        if calls is not None:
            self.message_metadata["tool_calls"] = calls
        elif "tool_calls" in self.message_metadata:
            del self.message_metadata["tool_calls"]


class ConversationSummary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    summary_content: str
    messages_summarized: int = Field(default=0)
    model_used: Optional[str] = Field(default=None, max_length=100)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
