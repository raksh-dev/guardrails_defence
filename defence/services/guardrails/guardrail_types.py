"""
Guardrail type definitions.

This module is intentionally dependency-light so every guard and every caller
can import it without circular-import risk. It defines:

* ``GuardName``     - which guardrail blocked a request.
* ``BlockReason``   - the category of the violation.
* ``GuardResult``   - the value object returned by every guard check.
* ``enforce()``     - raise ``GuardrailBlockedException`` if a result is blocked.

The actual exception lives in ``core.exceptions`` so it sits alongside the
rest of the project's exception hierarchy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GuardName(str, Enum):
    """Identifies which guardrail produced a decision."""
    INPUT_GUARD = "INPUT_GUARD"
    DOCUMENT_GUARD = "DOCUMENT_GUARD"
    CONVERSATION_HISTORY_GUARD = "CONVERSATION_HISTORY_GUARD"
    OUTPUT_GUARD = "OUTPUT_GUARD"
    TOOL_CALL_GUARD = "TOOL_CALL_GUARD"
    SUMMARY_QUALITY_GUARD = "SUMMARY_QUALITY_GUARD"


class BlockReason(str, Enum):
    """Why a request/response was blocked (safe to expose to the client)."""
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    HIDDEN_INSTRUCTIONS = "HIDDEN_INSTRUCTIONS"
    CONTEXT_POISONING = "CONTEXT_POISONING"
    DOCUMENT_INJECTION = "DOCUMENT_INJECTION"
    SYSTEM_PROMPT_LEAK = "SYSTEM_PROMPT_LEAK"
    SECRET_LEAK_ATTEMPT = "SECRET_LEAK_ATTEMPT"
    UNAUTHORIZED_TOOL_CALL = "UNAUTHORIZED_TOOL_CALL"
    LOW_QUALITY_SUMMARY = "LOW_QUALITY_SUMMARY"


# Default, user-safe messages per guard. These never expose internal details
# (no system prompts, no secrets, no raw user/PDF text, no stack traces).
_DEFAULT_MESSAGES: dict[GuardName, str] = {
    GuardName.INPUT_GUARD: (
        "The request was blocked because it contains suspicious "
        "prompt-injection instructions."
    ),
    GuardName.DOCUMENT_GUARD: (
        "The request was blocked because the document content contains "
        "instructions that try to manipulate the assistant."
    ),
    GuardName.CONVERSATION_HISTORY_GUARD: (
        "The request was blocked because earlier messages in this "
        "conversation attempt to override the assistant's instructions."
    ),
    GuardName.OUTPUT_GUARD: (
        "The model response was blocked because it may contain unsafe or "
        "internal information."
    ),
    GuardName.TOOL_CALL_GUARD: (
        "A state-changing action was blocked because the request appears to "
        "originate from manipulated instructions."
    ),
    GuardName.SUMMARY_QUALITY_GUARD: (
        "The generated answer was empty or too short to be a valid response."
    ),
}


@dataclass
class GuardResult:
    """Outcome of a single guardrail check."""
    blocked: bool
    guard: Optional[GuardName] = None
    reason: Optional[BlockReason] = None
    message: str = ""
    # Diagnostics — only ever surfaced when GUARDRAILS_DEBUG is enabled.
    stage: Optional[str] = None
    matched_category: Optional[str] = None

    @classmethod
    def ok(cls) -> "GuardResult":
        """A passing result."""
        return cls(blocked=False)

    @classmethod
    def block(
        cls,
        guard: GuardName,
        reason: BlockReason,
        *,
        stage: Optional[str] = None,
        matched_category: Optional[str] = None,
        message: Optional[str] = None,
    ) -> "GuardResult":
        """A blocking result with a safe, user-facing message."""
        return cls(
            blocked=True,
            guard=guard,
            reason=reason,
            stage=stage,
            matched_category=matched_category,
            message=message or _DEFAULT_MESSAGES.get(guard, "Request blocked by guardrails."),
        )

    def to_response(self, debug: bool = False) -> dict:
        """
        Render this result as the uniform guardrail JSON body.

        When ``debug`` is False (production / default) only safe fields are
        returned. When True (local Swagger testing) a small ``debug`` block
        with the stage and matched rule category is added — but never any raw
        prompt text, PDF content, secrets, or stack traces.
        """
        body: dict = {
            "success": False,
            "blocked": True,
            "guardrail": self.guard.value if self.guard else None,
            "reason": self.reason.value if self.reason else None,
            "message": self.message,
        }
        if debug:
            body["debug"] = {
                "stage": self.stage,
                "matched_category": self.matched_category,
            }
        return body


def enforce(result: GuardResult) -> None:
    """
    Raise ``GuardrailBlockedException`` if ``result`` is a block, otherwise
    do nothing. Centralising this keeps every caller a single line:

        enforce(input_guard.check_user_prompt(text))
    """
    if not result.blocked:
        return

    # Imported lazily to avoid any import-order coupling with core.exceptions.
    from core.exceptions import GuardrailBlockedException

    raise GuardrailBlockedException(
        guard=result.guard.value if result.guard else "GUARDRAIL",
        reason=result.reason.value if result.reason else None,
        message=result.message,
        debug={"stage": result.stage, "matched_category": result.matched_category},
    )
