"""
OutputGuard

Inspects LLM responses *before* they are returned to the client and blocks
output that appears to:

* reveal a system / developer / hidden prompt,
* leak API keys, tokens, secrets or environment variables,
* admit it ignored the user and followed hidden/PDF instructions.

It also provides a simple **summary-quality** check that rejects empty or
absurdly short answers (useful for the RAG "summarise this book" flow).
"""
import logging
from typing import Optional

from services.guardrails import patterns
from services.guardrails.guardrail_types import BlockReason, GuardName, GuardResult

logger = logging.getLogger(__name__)


class OutputGuard:
    def __init__(self, enabled: bool = True, min_summary_length: int = 20):
        self.enabled = enabled
        self.min_summary_length = min_summary_length

    def check_output(self, text: Optional[str]) -> GuardResult:
        """Block responses that leak prompts/secrets or admit manipulation."""
        if not self.enabled or not text:
            return GuardResult.ok()

        match = patterns.scan_output(text)
        if match:
            category, reason = match
            logger.warning("OutputGuard blocked model response (category=%s)", category)
            return GuardResult.block(
                GuardName.OUTPUT_GUARD, reason,
                stage="llm_output", matched_category=category,
            )
        return GuardResult.ok()

    def check_summary_quality(self, text: Optional[str]) -> GuardResult:
        """
        Reject empty / extremely short answers. This is intentionally simple:
        it guards against a model that returns nothing meaningful (e.g. when a
        PDF has no usable text or an injection caused a non-answer).
        """
        if not self.enabled:
            return GuardResult.ok()

        cleaned = (text or "").strip()
        if len(cleaned) < self.min_summary_length:
            logger.warning("SummaryQualityGuard blocked short answer (len=%d)", len(cleaned))
            return GuardResult.block(
                GuardName.SUMMARY_QUALITY_GUARD, BlockReason.LOW_QUALITY_SUMMARY,
                stage="llm_output", matched_category="too_short",
            )
        return GuardResult.ok()
