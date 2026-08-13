from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class AppSettings(BaseSettings):
    DEBUG: bool = False
    DATABASE_URL: Optional[str] = None

    STORAGE_URL: str
    STORAGE_ACCOUNT_SECRET: str
    STORAGE_BUCKET_NAME: str
    STORAGE_PRESIGNED_URL_EXPIRY: int = 3600

    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = ["pdf"]
    ALLOWED_MIME_TYPES: list[str] = ["application/pdf"]

    DEFAULT_LOAN_DAYS: int = 14
    MAX_LOAN_DAYS: int = 30

    # LLM Chat Settings
    # Provider: openrouter | openai | groq | together | deepseek | custom
    #           (all OpenAI-compatible) | ollama (local) | google | anthropic
    LLM_PROVIDER: str = "openrouter"
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"  # used by OpenAI-compatible providers
    LLM_MODEL: str = "openai/gpt-4o-mini"               # override with a :free model in .env for free testing
    LLM_API_KEY: str
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2048
    LLM_MAX_RETRIES: int = 3
    LLM_REQUEST_TIMEOUT: int = 60

    # Conversation Context Settings
    CONTEXT_WINDOW_SIZE: int = 20
    SUMMARIZATION_THRESHOLD: int = 15
    SUMMARY_MODEL: str = "openai/gpt-4o-mini"


    # RAG Embedding Settings
    EMBEDDING_PROVIDER: str = "openrouter"               # openai | openrouter | ollama | google
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_BASE_URL: str = "https://openrouter.ai/api/v1"
    EMBEDDING_DIMENSIONS: int = 1536

    # Ollama Settings (used when EMBEDDING_PROVIDER=ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # RAG Chunking Settings
    RAG_SPLITTER_TYPE: str = "recursive"             # recursive | character | token
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200

    # RAG Retrieval Settings
    RAG_TOP_K: int = 5
    RAG_SIMILARITY_THRESHOLD: float = 0.3

    # Supabase project base URL for PostgREST / vector store
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None

    # Vector Store Settings
    VECTOR_TABLE_NAME: str = "book_chunks"
    VECTOR_QUERY_FUNCTION: str = "match_book_chunks"

    # Guardrail Settings
    GUARDRAILS_ENABLED: bool = True                 # master on/off switch
    GUARDRAILS_DEBUG: bool = False                  # add safe diagnostics to block responses (local only)
    GUARDRAILS_MIN_SUMMARY_LENGTH: int = 20         # min chars for a valid RAG answer
    GUARDRAILS_BLOCK_MUTATING_TOOLS_ON_INJECTION: bool = True  # block create_loan/extend_loan on poisoned context

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings: AppSettings = AppSettings() # type - ignore