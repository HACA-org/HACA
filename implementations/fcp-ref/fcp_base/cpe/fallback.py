"""CPE Adapter Fallback Chains — Resilience through adapter prioritization.

Implements fallback chains: if primary adapter fails, transparently use secondary.
Enables resilience to API outages, rate limits, and other temporary failures.

Date: 2026-03-21
"""

from __future__ import annotations

import logging
from typing import Any

from .base import CPEAdapter, CPEError, CPEResponse

logger = logging.getLogger(__name__)


class FallbackChain:
    """Fallback chain for resilient adapter selection.

    Tries each adapter in order until one succeeds.
    Logs failures and tracks fallback events.
    """

    def __init__(self, adapters: list[tuple[str, CPEAdapter]], retries: int = 1) -> None:
        """Initialize fallback chain.

        Args:
            adapters: List of (name, adapter) tuples in priority order
            retries: Number of retries per adapter on transient failures
        """
        if not adapters:
            raise ValueError("At least one adapter required")

        self.adapters = adapters
        self.retries = retries
        self.fallback_events: list[dict[str, Any]] = []

    def invoke(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[CPEResponse, str]:
        """Invoke adapters in chain order until one succeeds.

        Args:
            system: System prompt
            messages: Chat history
            tools: Tool declarations

        Returns:
            Tuple of (response, adapter_name) from first successful adapter
        """
        if tools is None:
            tools = []

        last_error = None
        for i, (name, adapter) in enumerate(self.adapters):
            try:
                logger.debug(f"[FallbackChain] Trying {name} (adapter {i + 1}/{len(self.adapters)})")
                response = adapter.invoke(system, messages, tools)
                if i > 0:
                    # Logged fallback (wasn't primary)
                    self.fallback_events.append({
                        "primary_adapter": self.adapters[0][0],
                        "fallback_to": name,
                        "attempt": i,
                    })
                    logger.info(f"[FallbackChain] Fell back to {name} after {self.adapters[0][0]} failed")
                return response, name
            except CPEError as e:
                last_error = e
                logger.warning(f"[FallbackChain] {name} failed: {e}")
                continue
            except Exception as e:
                last_error = e
                logger.error(f"[FallbackChain] Unexpected error in {name}: {e}")
                continue

        # All adapters failed
        error_msg = f"All {len(self.adapters)} adapters in fallback chain failed"
        if last_error:
            error_msg += f": {last_error}"
        raise CPEError(error_msg)

    def get_fallback_summary(self) -> dict[str, Any]:
        """Get summary of fallback events."""
        return {
            "total_fallbacks": len(self.fallback_events),
            "primary_adapter": self.adapters[0][0] if self.adapters else None,
            "fallback_events": self.fallback_events,
        }

    def reset_fallback_history(self) -> None:
        """Clear fallback event history."""
        self.fallback_events = []


def build_fallback_chain(
    *adapter_names_and_instances: tuple[str, CPEAdapter],
) -> FallbackChain:
    """Build fallback chain from variable arguments.

    Args:
        *adapter_names_and_instances: Tuples of (name, adapter_instance)

    Returns:
        FallbackChain configured with given adapters

    Example:
        chain = build_fallback_chain(
            ("openai", openai_adapter),
            ("anthropic", anthropic_adapter),
            ("ollama", ollama_adapter),
        )
    """
    adapters = list(adapter_names_and_instances)
    return FallbackChain(adapters)


def create_recommended_chain() -> FallbackChain:
    """Create recommended fallback chain for resilience.

    Primary: OpenAI (fast, reliable)
    Secondary: Anthropic (best reasoning, slower)
    Tertiary: Ollama (local, no API costs)

    Note: Requires that adapters are initialized externally.
    This is a reference implementation; actual chain depends on user config.

    Raises:
        ImportError: If adapters not available
    """
    try:
        from .openai import OpenAIAdapter
        from .anthropic import AnthropicAdapter
        from .ollama import OllamaAdapter

        return FallbackChain([
            ("openai", OpenAIAdapter()),
            ("anthropic", AnthropicAdapter()),
            ("ollama", OllamaAdapter()),
        ])
    except ImportError as e:
        raise ImportError(f"Cannot create recommended chain: {e}") from e
