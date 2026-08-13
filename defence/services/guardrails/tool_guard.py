"""
ToolGuard

Protects LLM tool/function calling. It makes an explicit distinction between
**read-only** tools (safe to call) and **mutating** tools (change database
state) and blocks mutating tool calls whenever the surrounding conversation
shows prompt-injection indicators.

This is a defense-in-depth layer. In the normal pipeline the InputGuard
already blocks an injected request before the model runs, so the model never
gets the chance to emit a poisoned tool call. ToolGuard is the last line of
defense: if the text scanners are ever loosened/disabled, a state-changing
tool call originating from a manipulated context is still refused.
"""
import logging
from typing import Optional, Sequence

from services.guardrails import patterns
from services.guardrails.guardrail_types import BlockReason, GuardName, GuardResult

logger = logging.getLogger(__name__)

# Read-only tools: safe to execute, never mutate state.
READ_ONLY_TOOLS: frozenset[str] = frozenset({
    "search_books",
    "check_availability",
    "get_member_loans",
    "get_book_pdf_url",
    "calculate_late_fees",
})

# Mutating tools: change persistent state — must be protected.
MUTATING_TOOLS: frozenset[str] = frozenset({
    "create_loan",
    "extend_loan",
})


def _tool_name(call) -> Optional[str]:
    """Extract a tool name from the various shapes a tool call may take."""
    if isinstance(call, dict):
        return call.get("name") or call.get("function", {}).get("name")
    return getattr(call, "name", None)


class ToolGuard:
    def __init__(self, enabled: bool = True, block_mutating_on_injection: bool = True):
        self.enabled = enabled
        self.block_mutating_on_injection = block_mutating_on_injection

    @staticmethod
    def is_mutating(tool_name: Optional[str]) -> bool:
        return tool_name in MUTATING_TOOLS

    def check_tool_calls(
        self,
        tool_calls: Sequence,
        messages: Optional[Sequence] = None,
        context_flagged: bool = False,
    ) -> GuardResult:
        """
        Decide whether the requested tool calls are allowed.

        * ``tool_calls``      - tool calls the model wants to make.
        * ``messages``        - the conversation context (self-scanned for
                                injection if ``context_flagged`` is not set).
        * ``context_flagged`` - caller may pass True if it already detected
                                injection in the context.
        """
        if not self.enabled or not tool_calls:
            return GuardResult.ok()

        flagged = context_flagged
        category: Optional[str] = None
        if not flagged and messages:
            for msg in messages:
                if getattr(msg, "role", None) == "assistant":
                    continue
                hit = patterns.scan_input(getattr(msg, "content", "") or "")
                if hit:
                    flagged = True
                    category = hit[0]
                    break

        if not flagged or not self.block_mutating_on_injection:
            return GuardResult.ok()

        for call in tool_calls:
            name = _tool_name(call)
            if self.is_mutating(name):
                logger.warning("ToolGuard blocked mutating tool '%s' on flagged context", name)
                return GuardResult.block(
                    GuardName.TOOL_CALL_GUARD, BlockReason.UNAUTHORIZED_TOOL_CALL,
                    stage="tool_execution", matched_category=category or name,
                )
        return GuardResult.ok()
