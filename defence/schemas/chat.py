from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"] = "user"
    content: str

    @field_validator("content", mode="before")
    @classmethod
    def content_not_empty(cls, v):
        if not v or str(v).strip() == "":
            raise ValueError("message content must not be empty")
        return str(v).strip()


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        ..., min_length=1, description="Conversation history — last item is the new user message"
    )
    model: Optional[str] = Field(
        None, description="Override the default model"
    )
    provider: Optional[str] = Field(
        None, description="Override the default provider"
    )
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=16384)


class ChatResponse(BaseModel):
    id: str = Field(description="Unique response identifier")
    model: str = Field(description="Model that generated the response")
    provider: str
    message: ChatMessage
    usage: Optional["TokenUsage"] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TokenUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


# Needed for forward reference resolution
ChatResponse.model_rebuild()
