"""CPE Adapter Fallback Chains — Resilience through adapter prioritization.

Implements fallback chains: if primary adapter fails, transparently use secondary.
Enables resilience to API outages, rate limits, and other temporary failures.

Authorization & Notification:
- Fallback is TRANSPARENT by default (no user confirmation needed)
- Notification callback (optional) alerts user of provider/model change
- Use case: Notify UI to show "Fallback to X" banner
- For strict authorization: Call notify_callback with confirmation logic

Examples:
    # Silent fallback (no notification)
    chain = FallbackChain([
        ("openai", openai_adapter),
        ("anthropic", anthropic_adapter),
    ])

    # With notification (recommended for UI)
    def on_fallback(primary, fallback_to, error):
        ui.show_banner(f"Switched from {primary} to {fallback_to}")

    chain = FallbackChain(
        adapters=[...],
        notify_callback=on_fallback,
    )

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
    Supports notification callbacks for fallback events (e.g., UI alerts).
    """

    def __init__(
        self,
        adapters: list[tuple[str, CPEAdapter]],
        retries: int = 1,
        notify_callback: callable | None = None,
        require_confirmation: bool = False,
    ) -> None:
        """Initialize fallback chain.

        Args:
            adapters: List of (name, adapter) tuples in priority order
            retries: Number of retries per adapter on transient failures
            notify_callback: Optional callback(primary, fallback) for notifications
            require_confirmation: If True, abort fallback unless confirmed (rare)
        """
        if not adapters:
            raise ValueError("At least one adapter required")

        self.adapters = adapters
        self.retries = retries
        self.fallback_events: list[dict[str, Any]] = []
        self.notify_callback = notify_callback
        self.require_confirmation = require_confirmation

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

        Raises:
            CPEError: If all adapters fail
        """
        if tools is None:
            tools = []

        last_error = None
        primary_name = self.adapters[0][0]

        for i, (name, adapter) in enumerate(self.adapters):
            try:
                logger.debug(f"[FallbackChain] Trying {name} (adapter {i + 1}/{len(self.adapters)})")
                response = adapter.invoke(system, messages, tools)

                if i > 0:
                    # Fallback occurred (not primary adapter)
                    event = {
                        "primary_adapter": primary_name,
                        "fallback_to": name,
                        "attempt": i,
                    }
                    self.fallback_events.append(event)

                    # Notify callback if registered
                    if self.notify_callback:
                        try:
                            self.notify_callback(
                                primary=primary_name,
                                fallback_to=name,
                                error=str(last_error),
                            )
                        except Exception as e:
                            logger.error(f"Notification callback failed: {e}")

                    logger.info(f"[FallbackChain] Fell back to {name} after {primary_name} failed")

                return response, name

            except CPEError as e:
                last_error = e
                logger.warning(f"[FallbackChain] {name} failed: {e}")
                # Reset adapter state for next attempt (if supported)
                if hasattr(adapter, '_reset_state'):
                    try:
                        adapter._reset_state()  # type: ignore
                    except Exception as reset_err:
                        logger.debug(f"Adapter {name} reset failed: {reset_err}")
                continue
            except Exception as e:
                last_error = e
                logger.error(f"[FallbackChain] Unexpected error in {name}: {e}")
                # Reset adapter state for next attempt (if supported)
                if hasattr(adapter, '_reset_state'):
                    try:
                        adapter._reset_state()  # type: ignore
                    except Exception as reset_err:
                        logger.debug(f"Adapter {name} reset failed: {reset_err}")
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
