from fastapi import APIRouter, Depends, status
from sqlmodel import Session
from database.db import get_session
from schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    ConversationHistoryResponse,
    UpdateEnabledTools,
)
from services.conversation_service import ConversationService
from services.context_manager import ContextManager
from services.chat_service import build_chat_service
from services.tool_calling_service import ToolCallingService
from services.langchain_llm_provider import build_llm_provider
from services.supabase_storage import SupabaseStorageService
from services.storage import StorageService
from schemas.chat import ChatRequest

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def get_conversation_service(session: Session = Depends(get_session)) -> ConversationService:
    return ConversationService(session)


def get_context_manager(session: Session = Depends(get_session)) -> ContextManager:
    return ContextManager(session)


def get_storage() -> SupabaseStorageService:
    return SupabaseStorageService()


@router.post(
    "/",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
)
def create_conversation(
    request: ConversationCreate,
    member_id: int = 1,  # TODO: Replace with actual auth
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    """
    Create a new conversation thread for a user.
    """
    conversation = service.create_conversation(
        member_id=member_id, title=request.title, metadata=request.metadata, enabled_tools=request.enabled_tools
    )
    return ConversationResponse(
        id=conversation.id,
        member_id=conversation.member_id,
        title=conversation.title,
        metadata=conversation.conversation_metadata,
        enabled_tools=conversation.enabled_tools,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
    )


@router.get(
    "/",
    response_model=list[ConversationResponse],
    summary="List all conversations for a user",
)
def list_conversations(
    member_id: int = 1,  # TODO: Replace with actual auth
    limit: int = 50,
    offset: int = 0,
    service: ConversationService = Depends(get_conversation_service),
) -> list[ConversationResponse]:
    """
    Retrieve all conversations for the authenticated user.
    """
    conversations = service.list_conversations(member_id, limit, offset)
    return [
        ConversationResponse(
            id=conv.id,
            member_id=conv.member_id,
            title=conv.title,
            metadata=conv.conversation_metadata,
            enabled_tools=conv.enabled_tools,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=service.count_messages(conv.id),
        )
        for conv in conversations
    ]


@router.get(
    "/{conversation_id}",
    response_model=ConversationHistoryResponse,
    summary="Get conversation history",
)
def get_conversation_history(
    conversation_id: int,
    member_id: int = 1,  # TODO: Replace with actual auth
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationHistoryResponse:
    """
    Retrieve full conversation history including all messages.
    """
    conversation = service.get_conversation(conversation_id, member_id)
    messages = service.get_messages(conversation_id)
    summary = service.get_latest_summary(conversation_id)

    return ConversationHistoryResponse(
        conversation=ConversationResponse(
            id=conversation.id,
            member_id=conversation.member_id,
            title=conversation.title,
            metadata=conversation.conversation_metadata,
            enabled_tools=conversation.enabled_tools,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=len(messages),
        ),
        messages=[
            MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                model_used=msg.model_used,
                provider_used=msg.provider_used,
                token_usage=msg.token_usage,
                tool_calls=msg.tool_calls,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
        has_summary=summary is not None,
        total_messages=len(messages),
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message in a conversation",
)
async def send_message(
    conversation_id: int,
    request: MessageCreate,
    member_id: int = 1,  # TODO: Replace with actual auth
    service: ConversationService = Depends(get_conversation_service),
    context_mgr: ContextManager = Depends(get_context_manager),
    session: Session = Depends(get_session),
    storage: StorageService = Depends(get_storage),
) -> MessageResponse:
    """
    Send a message in an existing conversation and get LLM response.

    This endpoint:
    1. Stores the user's message
    2. Builds context using sliding window + summarization
    3. Gets LLM response (with or without tools)
    4. Stores the assistant's response
    5. Auto-summarizes if threshold is reached
    """
    conversation = service.get_conversation(conversation_id, member_id)

    user_message = service.add_message(
        conversation_id=conversation_id, role="user", content=request.content
    )

    context = context_mgr.build_context(conversation_id)

    # Determine if we should use tool calling
    if request.enable_tools and conversation.enabled_tools:
        # Use tool calling service
        llm_provider = build_llm_provider(
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        tool_service = ToolCallingService(
            session=session,
            storage=storage,
            llm_provider=llm_provider,
            enabled_tools=conversation.enabled_tools,
        )
        
        response_content, tool_calls = await tool_service.complete_with_tools(
            messages=context,
        )
        
        assistant_message = service.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_content,
            model_used=llm_provider.model_name,
            provider_used=llm_provider.provider_name,
            tool_calls=tool_calls,
        )
    else:
        # Use regular chat service
        chat_service = build_chat_service(
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        chat_request = ChatRequest(messages=context, provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,)
        response = await chat_service.acomplete(chat_request)

        assistant_message = service.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response.message.content,
            model_used=response.model,
            provider_used=response.provider,
            token_usage=response.usage.dict() if response.usage else None,
        )

    if context_mgr.should_summarize(conversation_id):
        await context_mgr.create_summary(conversation_id, model=request.model)

    return MessageResponse(
        id=assistant_message.id,
        conversation_id=assistant_message.conversation_id,
        role=assistant_message.role,
        content=assistant_message.content,
        model_used=assistant_message.model_used,
        provider_used=assistant_message.provider_used,
        token_usage=assistant_message.token_usage,
        tool_calls=assistant_message.tool_calls,
        created_at=assistant_message.created_at,
    )


@router.patch(
    "/{conversation_id}/tools",
    response_model=ConversationResponse,
    summary="Update enabled tools for a conversation",
)
def update_conversation_tools(
    conversation_id: int,
    request: UpdateEnabledTools,
    member_id: int = 1,  # TODO: Replace with actual auth
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    """
    Update the list of enabled tools for a conversation.
    
    Set enabled_tools to null or empty list to disable all tools.
    """
    conversation = service.update_enabled_tools(
        conversation_id, member_id, request.enabled_tools
    )
    
    return ConversationResponse(
        id=conversation.id,
        member_id=conversation.member_id,
        title=conversation.title,
        metadata=conversation.conversation_metadata,
        enabled_tools=conversation.enabled_tools,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=service.count_messages(conversation.id),
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
)
def delete_conversation(
    conversation_id: int,
    member_id: int = 1,  # TODO: Replace with actual auth
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    """
    Delete a conversation and all its messages.
    """
    service.delete_conversation(conversation_id, member_id)
