"""
Session mode registry — process-global execution mode flag.

Tracks whether the current session is operator-driven (main:session) or
autonomous (auto:session). Kept in its own module so that approval.py,
cli.py, and any other cross-cutting component can import from here without
pulling in the full session loop.
"""

from __future__ import annotations

from enum import Enum


class SessionMode(Enum):
    """Session execution mode."""
    MAIN = "main"   # Operator directly (UI/TUI, Telegram, etc.)
    AUTO = "auto"   # Autonomous (cron, CMI delegate, etc.)


_session_mode: SessionMode = SessionMode.MAIN


def set_session_mode(mode: SessionMode) -> None:
    """Set the current session mode (MAIN or AUTO)."""
    global _session_mode
    _session_mode = mode


def get_session_mode() -> SessionMode:
    """Return the current session mode."""
    return _session_mode


def is_auto_session() -> bool:
    """Return True if currently in autonomous session (auto:session)."""
    return _session_mode == SessionMode.AUTO


def is_main_session() -> bool:
    """Return True if currently in operator-driven session (main:session)."""
    return _session_mode == SessionMode.MAIN
