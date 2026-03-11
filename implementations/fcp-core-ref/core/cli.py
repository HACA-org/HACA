"""CLI entry point — FCP-Core §12.

Comandos:
  fcp [entity-root]                → sessão plain (ANSI, zero deps)
  fcp tui [entity-root]            → sessão Rich TUI  (requer rich)
  fcp [entity-root] --notifications → mostra notificações pendentes
  fcp [entity-root] --status       → estado rápido da entidade

Quando entity-root é omitido, usa o directório corrente.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    raw = list(argv) if argv is not None else sys.argv[1:]

    # Detect "tui" subcommand before argparse so it doesn't clash with
    # the entity_root positional argument.
    tui_mode = bool(raw and raw[0] == "tui")
    if tui_mode:
        raw = raw[1:]

    parser = argparse.ArgumentParser(
        prog="fcp" + (" tui" if tui_mode else ""),
        description="Filesystem Cognitive Platform — FCP-Core reference implementation",
    )
    parser.add_argument(
        "entity_root",
        nargs="?",
        default=".",
        help="Path to the FCP entity root (default: current directory)",
    )
    parser.add_argument(
        "--notifications",
        action="store_true",
        help="Print pending Operator notifications and exit",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print a quick status summary of the entity and exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print each cycle's messages and raw CPE response",
    )

    args = parser.parse_args(raw)
    root = Path(args.entity_root).resolve()

    if not root.exists():
        print(f"error: entity root not found: {root}", file=sys.stderr)
        return 1

    if args.notifications:
        return _cmd_notifications(root)

    if args.status:
        return _cmd_status(root)

    if tui_mode:
        return _cmd_tui(root, verbose=args.verbose)

    return _cmd_session(root, verbose=args.verbose)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_notifications(root: Path) -> int:
    from .operator import print_notifications
    print_notifications(root)
    return 0


def _cmd_status(root: Path) -> int:
    """Print a quick entity status summary."""
    from .sil import (
        check_distress_beacon,
        has_unresolved_critical,
        is_session_active,
        read_session_token,
    )
    from .fs import read_json

    print(f"\nEntity root: {root}")

    # Imprint
    imprint_path = root / "memory" / "imprint.json"
    if imprint_path.exists():
        try:
            imprint = read_json(imprint_path)
            eid = imprint.get("entity_id", "?")
            ts  = imprint.get("activated_at", "?")
            op  = imprint.get("operator_bound", {}).get("name", "?")
            print(f"  entity_id:    {eid}")
            print(f"  activated_at: {ts}")
            print(f"  operator:     {op}")
        except Exception:
            print("  imprint.json: [malformed]")
    else:
        print("  imprint.json: absent (cold-start pending)")

    # Session token
    token = read_session_token(root)
    if token is None:
        print("  session:      inactive")
    elif "revoked_at" in token:
        print(f"  session:      revoked ({token['session_id'][:8]}…)")
    else:
        print(f"  session:      active  ({token['session_id'][:8]}…)")

    # Distress beacon
    if check_distress_beacon(root):
        print("  beacon:       ACTIVE ⚠")
    else:
        print("  beacon:       clear")

    # Unresolved criticals
    if has_unresolved_critical(root):
        print("  criticals:    UNRESOLVED ⚠")
    else:
        print("  criticals:    none")

    print()
    return 0


def _boot_entity(root: Path) -> "BootContext | None":
    """Run FAP if needed, then boot.  Returns BootContext or None on failure."""
    from .fap import is_cold_start, run_fap, FAPError
    from .boot import run_boot, BootError

    if is_cold_start(root):
        print(f"\nFCP-Core — First Activation Protocol")
        print(f"Entity root: {root}\n")
        try:
            run_fap(root)
        except FAPError as exc:
            print(f"\n[FAP FAILED] {exc}", file=sys.stderr)
            return None
        from .sil import remove_session_token
        remove_session_token(root)

    try:
        return run_boot(root)
    except BootError as exc:
        print(f"\n[BOOT FAILED] {exc}", file=sys.stderr)
        return None


def _cmd_session(root: Path, verbose: bool = False) -> int:
    """Boot the entity and start a plain (ANSI) interactive session."""
    from .session import run_session
    from .ui import PlainUI

    ctx = _boot_entity(root)
    if ctx is None:
        return 1

    run_session(ctx, ui=PlainUI(verbose=verbose))
    return 0


def _cmd_tui(root: Path, verbose: bool = False) -> int:
    """Boot the entity and start a Rich TUI session."""
    from .session import run_session

    try:
        from .tui import RichUI
    except ImportError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1

    ctx = _boot_entity(root)
    if ctx is None:
        return 1

    run_session(ctx, ui=RichUI(verbose=verbose))
    return 0
