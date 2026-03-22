"""
Operator approval gate — FCP §10.6

Provides a single reusable entry point for any component that needs to request
on-the-fly operator authorization before proceeding.

Behaviour depends on session mode and TTY availability:

  main:session + TTY  — blocks and prompts the operator interactively via the
                        terminal picker.  Returns the operator's decision.

  main:session no TTY — writes a notification to state/operator_notifications/
                        and returns DENY (operator is not at the terminal).

  auto:session        — writes a notification to state/operator_notifications/
                        and returns DENY immediately (no interactive prompt).

Usage::

    from fcp_base.approval import request_approval, ApprovalDecision

    decision = request_approval(
        layout,
        subject="web_fetch",
        detail=url,
        prompt="Allow this URL?",
        options=("allow_once", "allow_always", "deny"),
        notification_severity="web_fetch_blocked",
        notification_payload={...},
    )
    if decision == ApprovalDecision.DENY:
        return original_error_output
"""

from __future__ import annotations

import sys
import time
from enum import Enum
from typing import TYPE_CHECKING

from . import ui
from .session import is_auto_session

if TYPE_CHECKING:
    from .store import Layout


class ApprovalDecision(str, Enum):
    ALLOW_ONCE   = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY         = "deny"


# Menu label → ApprovalDecision mapping.  The first character of each label is
# used as the keyboard shortcut when the terminal is not a TTY.
_OPTION_LABELS: dict[str, tuple[str, ApprovalDecision]] = {
    "allow_once":   ("y — allow once",                  ApprovalDecision.ALLOW_ONCE),
    "allow_always": ("a — allow always (add to allowlist)", ApprovalDecision.ALLOW_ALWAYS),
    "deny":         ("N — deny",                        ApprovalDecision.DENY),
}


def request_approval(
    layout: "Layout",
    *,
    subject: str,
    detail: str,
    prompt: str,
    options: tuple[str, ...] = ("allow_once", "allow_always", "deny"),
    notification_severity: str,
    notification_payload: dict,
) -> ApprovalDecision:
    """Request operator authorization for a blocked action.

    Args:
        layout:                  Entity layout (used to write notifications).
        subject:                 Component name, e.g. "shell_run" or "web_fetch".
        detail:                  The value being gated, e.g. the command or URL.
        prompt:                  Question shown to the operator, e.g. "Allow this URL?".
        options:                 Ordered tuple of option keys from
                                 ("allow_once", "allow_always", "deny").
                                 "deny" must always be present.
        notification_severity:   Severity tag used as the filename suffix when
                                 writing the auto:session notification.
        notification_payload:    Payload dict written to the notification file.

    Returns:
        ApprovalDecision — the operator's choice, or DENY if no TTY / auto:session.
    """
    if "deny" not in options:
        raise ValueError("'deny' must be included in options")

    no_tty = not sys.stdin.isatty()

    if is_auto_session() or no_tty:
        return _notify_and_deny(layout, subject, detail, notification_severity, notification_payload)

    return _interactive_prompt(subject, detail, prompt, options)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _notify_and_deny(
    layout: "Layout",
    subject: str,
    detail: str,
    severity: str,
    payload: dict,
) -> ApprovalDecision:
    """Write an operator notification and return DENY without prompting."""
    from .sil import write_notification
    ui.print_warn(f"{subject} blocked — notification written: {detail!r}")
    write_notification(layout, severity=severity, payload=payload)
    return ApprovalDecision.DENY


def _interactive_prompt(
    subject: str,
    detail: str,
    prompt: str,
    options: tuple[str, ...],
) -> ApprovalDecision:
    """Render an interactive terminal prompt and return the operator's decision."""
    labels = [_OPTION_LABELS[opt][0] for opt in options]
    decisions = [_OPTION_LABELS[opt][1] for opt in options]
    deny_idx = options.index("deny")

    _REV = "\x1b[7m"
    _RST = "\x1b[27m"
    print()
    ui.hr("OPERATOR ACTION REQUIRED")
    print()
    print(f"{_REV}  [!] {subject} blocked: {detail!r}{_RST}")
    print()

    try:
        choice = ui.pick_one(prompt, labels, default_idx=deny_idx, indent="  ")
        chosen_label = choice
        idx = labels.index(chosen_label)
    except (KeyboardInterrupt, EOFError, ValueError, IndexError):
        return ApprovalDecision.DENY

    return decisions[idx]
