"""
InputGuard

Inspects everything that flows *into* the LLM and blocks suspicious content
before the model is ever called:

* a single user prompt          -> :meth:`check_user_prompt`
* a full conversation history   -> :meth:`check_messages`
* untrusted PDF/book context    -> :meth:`check_document_context`

The guard is pattern-based (see :mod:`services.guardrails.patterns`) and
deliberately lightweight. It returns a :class:`GuardResult`; callers use
``enforce(...)`` to turn a block into the standard guardrail HTTP response.
"""
import logging
from typing import Optional, Sequence

from services.guardrails import patterns
from services.guardrails.guardrail_types import BlockReason, GuardName, GuardResult

logger = logging.getLogger(__name__)


class InputGuard:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    # -- single prompt -----------------------------------------------------

    def check_user_prompt(self, text: Optional[str], stage: str = "user_prompt") -> GuardResult:
        """Scan one user prompt (e.g. the RAG question, a chat message)."""
        if not self.enabled or not text:
            return GuardResult.ok()

        match = patterns.scan_input(text)
        if match:
            category, reason = match
            logger.warning("InputGuard blocked prompt at %s (category=%s)", stage, category)
            return GuardResult.block(
                GuardName.INPUT_GUARD, reason, stage=stage, matched_category=category
            )
        return GuardResult.ok()

    # -- full conversation history ----------------------------------------

    def check_messages(self, messages: Sequence) -> GuardResult:
        """
        Scan an ordered list of messages (objects with ``.role`` / ``.content``).

        * If the **last user message** is malicious it is treated as a direct
          attack -> ``INPUT_GUARD``.
        * If an **earlier** user/system message is malicious it is treated as
          distributed context poisoning -> ``CONVERSATION_HISTORY_GUARD``.

        Assistant messages are skipped here (model output is covered by the
        OutputGuard). This is the core of the "analyse the whole conversation"
        requirement: a benign current message is still blocked when an earlier
        turn tried to poison the context.
        """
        if not self.enabled or not messages:
            return GuardResult.ok()

        last_user_idx = None
        for i, msg in enumerate(messages):
            if getattr(msg, "role", None) == "user":
                last_user_idx = i

        for i, msg in enumerate(messages):
            role = getattr(msg, "role", None)
            content = getattr(msg, "content", "") or ""
            if role == "assistant":
                continue

            match = patterns.scan_input(content)
            if not match:
                continue

            category, reason = match
            if i == last_user_idx:
                logger.warning("InputGuard blocked current message (category=%s)", category)
                return GuardResult.block(
                    GuardName.INPUT_GUARD, reason,
                    stage="current_message", matched_category=category,
                )
            logger.warning("ConversationHistoryGuard blocked poisoned history (category=%s)", category)
            return GuardResult.block(
                GuardName.CONVERSATION_HISTORY_GUARD, BlockReason.CONTEXT_POISONING,
                stage="conversation_history", matched_category=category,
            )
        return GuardResult.ok()

    # -- untrusted document context ---------------------------------------

    def check_document_context(self, text: Optional[str]) -> GuardResult:
        """
        Scan PDF/book text that is about to be injected into the prompt as
        RAG context. Uses the stricter document rule set so ordinary prose
        is not over-blocked.
        """
        if not self.enabled or not text:
            return GuardResult.ok()

        match = patterns.scan_document(text)
        if match:
            category, _ = match
            logger.warning("DocumentGuard blocked PDF/RAG context (category=%s)", category)
            return GuardResult.block(
                GuardName.DOCUMENT_GUARD, BlockReason.DOCUMENT_INJECTION,
                stage="rag_context", matched_category=category,
            )
        return GuardResult.ok()
