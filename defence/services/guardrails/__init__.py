"""
Guardrails package.

A lightweight, modular layer that detects and mitigates prompt-injection
attacks across user prompts, conversation history, PDF/book content, LLM
output, and tool-calling workflows.

Usage from any service (routers stay thin and never import guard internals):

    from services.guardrails import input_guard, output_guard, tool_guard, enforce

    enforce(input_guard.check_user_prompt(question))
    answer = call_llm(...)
    enforce(output_guard.check_output(answer))

Ready-to-use singletons are configured from ``settings`` so the whole system
can be toggled with ``GUARDRAILS_ENABLED`` and tuned without touching code.
"""
from core.config import settings

from services.guardrails.guardrail_types import (
    BlockReason,
    GuardName,
    GuardResult,
    enforce,
)
from services.guardrails.input_guard import InputGuard
from services.guardrails.output_guard import OutputGuard
from services.guardrails.tool_guard import (
    MUTATING_TOOLS,
    READ_ONLY_TOOLS,
    ToolGuard,
)

# Shared, stateless singletons (the guards hold no per-request state).
input_guard = InputGuard(enabled=settings.GUARDRAILS_ENABLED)
output_guard = OutputGuard(
    enabled=settings.GUARDRAILS_ENABLED,
    min_summary_length=settings.GUARDRAILS_MIN_SUMMARY_LENGTH,
)
tool_guard = ToolGuard(
    enabled=settings.GUARDRAILS_ENABLED,
    block_mutating_on_injection=settings.GUARDRAILS_BLOCK_MUTATING_TOOLS_ON_INJECTION,
)

__all__ = [
    "input_guard",
    "output_guard",
    "tool_guard",
    "enforce",
    "GuardResult",
    "GuardName",
    "BlockReason",
    "InputGuard",
    "OutputGuard",
    "ToolGuard",
    "READ_ONLY_TOOLS",
    "MUTATING_TOOLS",
]
