from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import time
import logging

from core.config import settings
from core.exceptions import GuardrailBlockedException
from database.db import create_db_and_tables, verify_connection
from routers import books, member, loan, chat, conversation, rag

from core.utils import char_streamer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up")
    try:
        verify_connection()
        logger.info("Supabase connection OK.")
        create_db_and_tables()
        logger.info("Database tables ready.")
    except Exception as e:
        logger.error("Could not connect to Supabase: %s", e)
        raise
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Library Management System",
    description=(
        "A REST API for managing a library"
        "Built with FastAPI + Supabase"
    ),
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(GuardrailBlockedException)
async def guardrail_blocked_handler(request: Request, exc: GuardrailBlockedException):
    """
    Render a blocked-guardrail decision as a uniform, user-safe JSON envelope.

    The body never exposes system prompts, secrets, raw PDF/user text, or
    stack traces. Diagnostic fields are only added when GUARDRAILS_DEBUG=true.
    """
    body = {
        "success": False,
        "blocked": True,
        "guardrail": exc.guard,
        "reason": exc.reason,
        "message": exc.message,
    }
    if settings.GUARDRAILS_DEBUG:
        body["debug"] = exc.debug
    return JSONResponse(status_code=exc.status_code, content=body)


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.include_router(books.router)
app.include_router(member.router)
app.include_router(loan.router)
app.include_router(chat.router)
app.include_router(conversation.router)
app.include_router(rag.router)

@app.get("/", tags=["Health"])
def root():
    return {
        "service": "Library Management API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}

@app.get("/stream")
def stream_file():
    file_path = "sample.txt"
    return StreamingResponse(char_streamer(file_path), media_type="text/event-stream")

