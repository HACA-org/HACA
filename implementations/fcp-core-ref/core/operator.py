"""Operator Channel — FCP-Core §10.6.

Two primitives:
  1. terminal_prompt() — synchronous; used when the platform must wait
     for the Operator's response before proceeding.
  2. write_notification() — asynchronous; used for escalations and reports
     that do not require an immediate response.

Every invocation of either primitive is logged to state/integrity.log as an
ACP envelope (TYPE_MSG, actor=fcp) with the condition and delivery status.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

from .fs import utcnow_iso


# ---------------------------------------------------------------------------
# Terminal availability check
# ---------------------------------------------------------------------------

def assert_terminal_accessible() -> None:
    """Verify that stdin and stdout are accessible for interactive I/O (§10.6).

    Raises:
        OSError: if stdin or stdout are not accessible (e.g., captured streams,
                 redirected file descriptors, or test harness buffers).
    """
    try:
        sys.stdin.fileno()
        sys.stdout.fileno()
    except (AttributeError, io.UnsupportedOperation, OSError) as exc:
        raise OSError(f"Terminal prompt inaccessible: {exc}") from exc


# ---------------------------------------------------------------------------
# Terminal prompt  (synchronous)
# ---------------------------------------------------------------------------

def terminal_prompt(prompt: str, *, options: list[str] | None = None) -> str:
    """Present *prompt* to the Operator on stdout and read a line from stdin.

    Args:
        prompt:  The message to display.  Rendered with a blank line above
                 and below for readability.
        options: Optional list of acceptable answer strings.  If provided,
                 the prompt loops until the Operator enters one of them.
                 Match is case-insensitive.

    Returns:
        The stripped response string (lowercased if options are provided).

    Raises:
        EOFError: if stdin reaches EOF before a response is given (treated
                  by callers as the Operator explicitly closing the session).
    """
    print()
    print(prompt)
    if options:
        opt_str = " / ".join(f"[{o}]" for o in options)
        print(f"  Options: {opt_str}")
    print()

    while True:
        try:
            sys.stdout.write("  > ")
            sys.stdout.flush()
            line = sys.stdin.readline()
        except KeyboardInterrupt:
            print()
            continue

        if not line:
            raise EOFError("stdin closed")

        answer = line.strip()
        if options is None:
            return answer
        if answer.lower() in [o.lower() for o in options]:
            return answer.lower()
        print(f"  Please enter one of: {', '.join(options)}")


# ---------------------------------------------------------------------------
# Async notifications  (state/operator_notifications/)
# ---------------------------------------------------------------------------

SEVERITY_INFO     = "info"
SEVERITY_DEGRADED = "degraded"
SEVERITY_CRITICAL = "critical"


def write_notification(
    entity_root: str | Path,
    severity:    str,
    content:     str | dict[str, Any],
    *,
    component:   str = "fcp",
) -> Path:
    """Write a notification file to ``state/operator_notifications/``.

    File name: ``<ts>-<severity>-<component>.json`` (UTC timestamp ensures
    lexicographic order == arrival order).

    Args:
        entity_root: Path to the entity root directory.
        severity:    Severity label — use SEVERITY_* constants.
        content:     Notification body; str or dict (auto-serialised).
        component:   Component that raised the notification (default 'fcp').

    Returns:
        Path to the written notification file.
    """
    entity_root = Path(entity_root)
    notif_dir = entity_root / "state" / "operator_notifications"
    notif_dir.mkdir(parents=True, exist_ok=True)

    ts = utcnow_iso().replace(":", "").replace("-", "")  # compact for filename
    ts_full = utcnow_iso()
    filename = f"{ts_full}-{severity}-{component}.json"
    # Sanitise: replace colons (invalid on some FS) with underscores
    filename = filename.replace(":", "_")
    path = notif_dir / filename

    body: dict[str, Any] = {
        "ts": ts_full,
        "severity": severity,
        "component": component,
        "content": content,
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_notifications(entity_root: str | Path) -> list[dict[str, Any]]:
    """Return all pending notifications in timestamp order.

    Args:
        entity_root: Path to the entity root directory.

    Returns:
        List of notification dicts, sorted by filename (= arrival order).
    """
    entity_root = Path(entity_root)
    notif_dir = entity_root / "state" / "operator_notifications"
    if not notif_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(notif_dir.iterdir()):
        if path.is_file() and path.suffix == ".json":
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
    return results


def print_notifications(entity_root: str | Path) -> int:
    """Print all pending notifications to stdout.

    Returns:
        Number of notifications printed.
    """
    notifications = list_notifications(entity_root)
    if not notifications:
        print("No pending notifications.")
        return 0

    for n in notifications:
        ts        = n.get("ts", "?")
        severity  = n.get("severity", "?").upper()
        component = n.get("component", "?")
        content   = n.get("content", "")
        print(f"\n[{severity}] {ts} — {component}")
        if isinstance(content, dict):
            print(json.dumps(content, indent=2, ensure_ascii=False))
        else:
            print(f"  {content}")

    print()
    return len(notifications)
