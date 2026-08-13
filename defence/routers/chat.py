from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from schemas.chat import ChatRequest, ChatResponse
from services.chat_service import build_chat_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "/",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send messages and receive a complete LLM response",
)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Accepts a list of messages (conversation history) and returns the
    assistant's reply.  Optionally override ``provider``, ``model``,
    ``temperature``, or ``max_tokens`` per request.
    """
    service = build_chat_service(
        provider=request.provider,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return await service.acomplete(request)


@router.post(
    "/stream",
    status_code=status.HTTP_200_OK,
    summary="Stream LLM response as Server-Sent Events",
)
async def chat_stream(request: ChatRequest):
    """
    Same contract as ``POST /chat`` but returns a streaming response
    (``text/event-stream``).  Each chunk is a Server-Sent Event with the
    format ``data: <token>\\n\\n``.  The stream ends with ``data: [DONE]\\n\\n``.
    """
    service = build_chat_service(
        provider=request.provider,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return StreamingResponse(
        service.astream(request),
        media_type="text/event-stream",
    )
