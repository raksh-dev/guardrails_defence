from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    metadata: Optional[dict] = None
    enabled_tools: Optional[list[str]] = Field(
        default=None,
        description="List of tool names to enable for this conversation. Available: search_books, get_book_pdf_url, calculate_late_fees, create_loan, extend_loan"
    )


class ConversationResponse(BaseModel):
    id: int | None
    member_id: int
    title: str
    metadata: Optional[dict] = None
    enabled_tools: Optional[list[str]] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1)
    enable_tools: bool = Field(
        default=False,
        description="Enable function calling for this message using conversation's enabled_tools"
    )
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=16384)


class MessageResponse(BaseModel):
    id: int | None
    conversation_id: int
    role: str
    content: str
    model_used: Optional[str] = None
    provider_used: Optional[str] = None
    token_usage: Optional[dict] = None
    tool_calls: Optional[list[dict]] = None
    created_at: datetime


class ConversationHistoryResponse(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]
    has_summary: bool = False
    total_messages: int = 0


class UpdateEnabledTools(BaseModel):
    enabled_tools: Optional[list[str]] = Field(
        default=None,
        description="List of tool names to enable. Set to null or empty list to disable all tools."
    )
