"""
endpoint_test_utils.py
======================
Shared utilities for the adversarial prompt test platform.

Responsibilities
----------------
bootstrap_defence_app()
    Sets minimal stub environment variables (unless ``USE_REAL_SERVICES=true``),
    inserts ``defence/`` onto sys.path, and imports ``defence/main.py`` —
    returning the real FastAPI application with all guardrail middleware active.

attack/config.json
    Primary configuration file for the test platform. Set ``use_real_services``
    to ``true`` here to run against real defence services. Can be overridden via
    the ``USE_REAL_SERVICES`` environment variable.

USE_REAL_SERVICES
    Runtime toggle. When ``false`` (default), the test platform uses the fakes
    below so no live external services are needed. When ``true``, the real
    defence services are used (LLM, DB, vector store, storage) and a valid
    ``defence/.env`` with real credentials is required.

Fake / stub classes (used only when USE_REAL_SERVICES=false)
    ``FakeLLMProvider``         — returns a fixed string instead of calling an LLM API.
    ``FakeVectorStore``         — returns in-memory FakeDocument objects instead of pgvector.
    ``FakeRAGSession``          — satisfies SQLModel session type checks without a DB.
    ``FakeConversationService`` — in-memory conversation / message store.
    ``FakeContextManager``      — builds context from the in-memory store.

install_*() helpers
    No-ops when ``USE_REAL_SERVICES=true``. Otherwise they patch the defence
    router/service modules at runtime to use the fakes above, so guardrail logic
    (InputGuard, DocumentGuard, OutputGuard, ToolGuard) runs in full but no
    network calls are made.

load_all_evaluator_cases(file_name)
    Reads every case from the red-team-evaluator data directory.  The directory
    path can be overridden via the ``RED_TEAM_EVALUATOR_DIR`` environment variable.

EndpointCase / assert_response / print_report
    Thin test-assertion and reporting layer used by each endpoint test script.
    ``print_report`` distinguishes BLOCKED, GAP, FALSE-POS, ALLOWED, and
    TEST-FAIL rows and prints a semantic summary at the end.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFENCE_ROOT = PROJECT_ROOT / "defence"
DEFAULT_EVALUATOR_DIR = Path(__file__).resolve().parent
ATTACK_CONFIG_PATH = DEFAULT_EVALUATOR_DIR / "config.json"


def _load_attack_config() -> dict:
    """Load attack test platform configuration from attack/config.json."""
    if not ATTACK_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(ATTACK_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


_ATTACK_CONFIG = _load_attack_config()

# Set use_real_services to true in attack/config.json (or USE_REAL_SERVICES=true in the
# environment) to run against real defence services (real LLM, DB, vector store, storage).
# Requires a valid defence/.env with real credentials.
USE_REAL_SERVICES = os.environ.get(
    "USE_REAL_SERVICES", str(_ATTACK_CONFIG.get("use_real_services", False))
).lower() in ("true", "1", "yes")


def is_real_services_mode() -> bool:
    """Return True when the test platform is using real defence services."""
    return USE_REAL_SERVICES


def bootstrap_defence_app():
    """Set minimal env defaults, import defence/main.py, and return its app."""
    env_defaults = {
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
        "STORAGE_URL": "https://example.storage.supabase.co",
        "STORAGE_ACCOUNT_SECRET": "test-storage-secret",
        "STORAGE_BUCKET_NAME": "books",
        "LLM_API_KEY": "sk-test-not-real",
        "LLM_PROVIDER": "openrouter",
        "LLM_MODEL": "test-model",
        "GUARDRAILS_ENABLED": "true",
        "GUARDRAILS_DEBUG": "false",
    }
    if not USE_REAL_SERVICES:
        for key, value in env_defaults.items():
            os.environ[key] = value
        os.environ["DEBUG"] = "false"
    else:
        # Real mode: trust the user's environment / defence/.env. Only set DEBUG
        # if it is absent so the app doesn't crash.
        os.environ.setdefault("DEBUG", "false")

    defence_path = str(DEFENCE_ROOT)
    if defence_path not in sys.path:
        sys.path.insert(0, defence_path)

    import warnings
    warnings.filterwarnings("ignore")

    from main import app

    logging.disable(logging.CRITICAL)
    return app


def make_client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, raise_server_exceptions=False)


class FakeAIMessage:
    def __init__(self, content: str):
        self.content = content
        self.response_metadata = {
            "token_usage": {
                "prompt_tokens": 5,
                "completion_tokens": 7,
                "total_tokens": 12,
            }
        }


class FakeLLMProvider:
    provider_name = "fake"
    model_name = "fake-guardrail-model"

    def __init__(self, content: str):
        self.content = content
        self.chat_model = self

    def invoke(self, messages):
        return FakeAIMessage(self.content)

    async def ainvoke(self, messages):
        return FakeAIMessage(self.content)

    def bind_tools(self, tools):
        return self


def install_chat_stub(module: Any, output: str) -> None:
    if USE_REAL_SERVICES:
        return
    from services.chat_service import ChatService

    module.build_chat_service = lambda **kwargs: ChatService(FakeLLMProvider(output))


class FakeDocument:
    def __init__(self, content: str, book_id: int = 1):
        self.page_content = content
        self.metadata = {
            "book_id": book_id,
            "book_title": f"Book {book_id}",
            "page_number": 1,
            "chunk_index": 0,
        }


class FakeVectorStore:
    def __init__(self, documents: list[FakeDocument], score: float = 0.95):
        self.documents = documents
        self.score = score

    def similarity_search(self, query: str, top_k: int, filter: dict | None = None):
        return [(doc, self.score) for doc in self.documents[:top_k]]

    def delete_by_book_id(self, book_id: int) -> None:
        return None

    def add_documents(self, documents) -> int:
        return len(documents)


class _ExecResult:
    def __init__(self, value: Any):
        self.value = value

    def first(self):
        return self.value


class FakeRAGSession:
    def exec(self, statement):
        from models.book_embedding import BookIngestion, IngestionStatus

        return _ExecResult(
            BookIngestion(
                book_id=1,
                status=IngestionStatus.COMPLETED,
                total_chunks=1,
                total_pages=1,
            )
        )


def install_rag_service_override(app, output: str, documents: list[FakeDocument]) -> None:
    if USE_REAL_SERVICES:
        return
    import routers.rag as rag_router
    import services.rag.rag_service as rag_service_module
    from services.rag.rag_service import RAGService

    rag_service_module.build_llm_provider = lambda **kwargs: FakeLLMProvider(output)

    app.dependency_overrides[rag_router.get_rag_service] = lambda: RAGService(
        session=FakeRAGSession(),
        book_service=None,
        pdf_loader=None,
        chunker=None,
        vector_store=FakeVectorStore(documents),
    )


class InMemoryConversationStore:
    def __init__(self) -> None:
        self.conversations: dict[int, Any] = {}
        self.messages: dict[int, list[Any]] = {}
        self.next_conversation_id = 1
        self.next_message_id = 1


class FakeConversationService:
    def __init__(self, store: InMemoryConversationStore):
        self.store = store

    def create_conversation(
        self,
        member_id: int,
        title: str,
        metadata: dict | None = None,
        enabled_tools: list[str] | None = None,
    ):
        from models.conversation import Conversation

        metadata = dict(metadata or {})
        if enabled_tools is not None:
            metadata["enabled_tools"] = enabled_tools
        conversation = Conversation(
            id=self.store.next_conversation_id,
            member_id=member_id,
            title=title,
            conversation_metadata=metadata,
        )
        self.store.next_conversation_id += 1
        self.store.conversations[conversation.id] = conversation
        self.store.messages[conversation.id] = []
        return conversation

    def get_conversation(self, conversation_id: int, member_id: int):
        return self.store.conversations[conversation_id]

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        model_used: str | None = None,
        provider_used: str | None = None,
        token_usage: dict | None = None,
        tool_calls: list[dict] | None = None,
        metadata: dict | None = None,
    ):
        from models.conversation import Message

        msg_metadata = dict(metadata or {})
        if tool_calls is not None:
            msg_metadata["tool_calls"] = tool_calls
        message = Message(
            id=self.store.next_message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            model_used=model_used,
            provider_used=provider_used,
            token_usage=token_usage,
            message_metadata=msg_metadata,
            created_at=datetime.now(timezone.utc),
        )
        self.store.next_message_id += 1
        self.store.messages[conversation_id].append(message)
        return message

    def get_messages(self, conversation_id: int, limit: int | None = None, offset: int = 0):
        messages = self.store.messages[conversation_id][offset:]
        return messages[:limit] if limit else messages

    def get_latest_summary(self, conversation_id: int):
        return None

    def count_messages(self, conversation_id: int | None) -> int:
        if conversation_id is None:
            return 0
        return len(self.store.messages.get(conversation_id, []))


class FakeContextManager:
    def __init__(self, store: InMemoryConversationStore):
        self.store = store

    def build_context(self, conversation_id: int, include_system_prompt: bool = True):
        from schemas.chat import ChatMessage

        return [
            ChatMessage(role=message.role, content=message.content)
            for message in self.store.messages[conversation_id]
        ]

    def should_summarize(self, conversation_id: int) -> bool:
        return False

    async def create_summary(self, conversation_id: int, model: str | None = None) -> None:
        return None


def install_conversation_overrides(app, output: str) -> InMemoryConversationStore | None:
    if USE_REAL_SERVICES:
        return None
    import routers.conversation as conversation_router

    store = InMemoryConversationStore()
    conversation_service = FakeConversationService(store)
    context_manager = FakeContextManager(store)

    install_chat_stub(conversation_router, output)
    conversation_router.build_llm_provider = lambda **kwargs: FakeLLMProvider(output)

    app.dependency_overrides[conversation_router.get_conversation_service] = (
        lambda: conversation_service
    )
    app.dependency_overrides[conversation_router.get_context_manager] = lambda: context_manager
    app.dependency_overrides[conversation_router.get_session] = lambda: object()
    app.dependency_overrides[conversation_router.get_storage] = lambda: object()
    return store


def load_evaluator_cases(file_name: str, wanted_ids: list[str]) -> list[dict[str, Any]]:
    evaluator_dir = Path(os.environ.get("RED_TEAM_EVALUATOR_DIR", DEFAULT_EVALUATOR_DIR))
    data_path = evaluator_dir / "data" / file_name
    if not data_path.exists():
        return []

    import json

    data = json.loads(data_path.read_text(encoding="utf-8"))
    by_id = {case.get("id"): case for case in data}
    return [by_id[case_id] for case_id in wanted_ids if case_id in by_id]


def load_all_evaluator_cases(file_name: str) -> list[dict[str, Any]]:
    """Load every case from an evaluator data file."""
    evaluator_dir = Path(os.environ.get("RED_TEAM_EVALUATOR_DIR", DEFAULT_EVALUATOR_DIR))
    data_path = evaluator_dir / "data" / file_name
    if not data_path.exists():
        return []
    import json
    return json.loads(data_path.read_text(encoding="utf-8"))


@dataclass
class EndpointCase:
    case_id: str
    name: str
    request: dict[str, Any]
    # expected_status: the HTTP status the test EXPECTS.
    # For attack cases that slip through the guardrail, this is 200 — the
    # test PASSES when the attack succeeds (revealing a security gap).
    # For attack cases the guardrail should block, this is 400.
    expected_status: int
    expected_guardrail: str | None = None
    expected_reason: str | None = None
    # Human-readable note shown in the report
    gap_note: str | None = None
    setup: Callable[[], None] | None = None
    # Set True for cases that require fake LLM/DB responses and cannot run
    # against real defence services without redesign.
    skip_in_real_mode: bool = False


def assert_response(case: EndpointCase, response) -> tuple[bool, str]:
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}

    checks = [response.status_code == case.expected_status]
    details = [f"status {response.status_code}"]

    if case.expected_guardrail is not None:
        checks.append(body.get("blocked") is True)
        checks.append(body.get("guardrail") == case.expected_guardrail)
        details.append(f"guardrail {body.get('guardrail')}")

    if case.expected_reason is not None:
        checks.append(body.get("reason") == case.expected_reason)
        details.append(f"reason {body.get('reason')}")

    return all(checks), ", ".join(details)


def print_report(script_name: str, endpoint: str, rows: list[dict[str, Any]]) -> int:
    total = len(rows)
    skipped = sum(1 for r in rows if r.get("skipped"))
    # "passed" in test terms: the response matched what we expected
    passed = sum(1 for r in rows if r["passed"] and not r.get("skipped"))
    failed = total - passed - skipped

    # Semantic breakdown
    blocked_attacks = sum(1 for r in rows if r["passed"] and not r.get("skipped") and r.get("is_attack") and r.get("was_blocked"))
    slipped_attacks  = sum(1 for r in rows if r["passed"] and not r.get("skipped") and r.get("is_attack") and not r.get("was_blocked"))
    false_positives  = sum(1 for r in rows if r["passed"] and not r.get("skipped") and not r.get("is_attack") and r.get("was_blocked"))
    true_negatives   = sum(1 for r in rows if r["passed"] and not r.get("skipped") and not r.get("is_attack") and not r.get("was_blocked"))
    test_failures    = sum(1 for r in rows if not r["passed"] and not r.get("skipped"))

    print()
    print("=" * 80)
    print(f"{script_name} report")
    print(f"Endpoint : {endpoint}")
    print("=" * 80)

    for row in rows:
        if row.get("skipped"):
            marker = "SKIPPED  "      # requires fakes; cannot run against real services
        elif not row["passed"]:
            marker = "TEST-FAIL"      # test harness itself is broken
        elif row.get("is_attack") and not row.get("was_blocked"):
            marker = "GAP      "      # attack slipped through — security gap
        elif not row.get("is_attack") and row.get("was_blocked"):
            marker = "FALSE-POS"      # benign request wrongly blocked
        elif row.get("is_attack") and row.get("was_blocked"):
            marker = "BLOCKED  "      # attack correctly blocked
        else:
            marker = "ALLOWED  "      # benign correctly allowed

        note = f"  [{row['gap_note']}]" if row.get("gap_note") else ""
        print(f"[{marker}] {row['case_id']:<22} {row['name'][:45]:<45} ({row['details']}){note}")

    attack_total = blocked_attacks + slipped_attacks + test_failures
    print()
    print("-" * 80)
    print(f"Total test cases      : {total}")
    print(f"  Skipped (need fakes): {skipped}")
    print(f"  Attacks BLOCKED     : {blocked_attacks}   <- guardrail working")
    print(f"  Attacks SLIPPED     : {slipped_attacks}   <- SECURITY GAPS IDENTIFIED")
    print(f"  Benign TRUE-NEG     : {true_negatives}   <- correctly allowed")
    print(f"  Benign FALSE-POS    : {false_positives}   <- over-blocking (false alarms)")
    print(f"  Test harness errors : {test_failures}")
    print("=" * 80)
    # Return non-zero only if the harness itself broke (not for security gaps)
    return 0 if test_failures == 0 else 1
