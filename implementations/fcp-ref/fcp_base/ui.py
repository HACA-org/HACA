"""
UI helpers — shared terminal style, input primitives, and interactive pickers.

All user-facing output in fcp_base should go through this module so that
visual changes can be made in one place.
"""

from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# ANSI colour constants
# ---------------------------------------------------------------------------

RESET      = "\x1b[0m"
BOLD_CYAN  = "\x1b[1;96m"
DIM        = "\x1b[2m"
GRAY       = "\x1b[90m"

# ---------------------------------------------------------------------------
# Status prefixes
# ---------------------------------------------------------------------------

def ok(msg: str) -> str:
    return f"  [√] {msg}"

def warn(msg: str) -> str:
    return f"  [!] {msg}"

def err(msg: str) -> str:
    return f"  [ERROR] {msg}"

def info(msg: str) -> str:
    return f"  {msg}"

def print_ok(msg: str)   -> None: print(ok(msg))
def print_warn(msg: str) -> None: print(warn(msg))
def print_err(msg: str)  -> None: print(err(msg))
def print_info(msg: str) -> None: print(info(msg))

# ---------------------------------------------------------------------------
# Section dividers
# ---------------------------------------------------------------------------

_W = 60

def hr(label: str = "", width: int = _W) -> None:
    """Print a section divider, optionally with a label."""
    if label:
        pad = width - len(label) - 4
        print(f"\n  ── {label} {'─' * pad}")
    else:
        print(f"  {'─' * width}")

# ---------------------------------------------------------------------------
# Basic input primitives
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "") -> str:
    """Text input with an optional default shown in brackets."""
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
    except EOFError:
        val = ""
    return val or default


def confirm(prompt: str, default: bool = False, indent: str = "  ") -> bool:
    """
    Yes/No confirmation.
    - On a TTY: arrow-key picker via pick_one().
    - On non-TTY / pipe: plain [Y/n] / [y/N] text fallback.
    """
    if not sys.stdin.isatty():
        hint = "Y/n" if default else "y/N"
        try:
            val = input(f"{indent}{prompt} [{hint}]: ").strip().lower()
        except EOFError:
            val = ""
        if not val:
            return default
        return val.startswith("y")

    choice = pick_one(prompt, ["Yes", "No"], default_idx=(0 if default else 1), indent=indent)
    return choice == "Yes"


# ---------------------------------------------------------------------------
# Interactive pickers
# ---------------------------------------------------------------------------

def pick_one(prompt: str, items: list[str], default_idx: int = 0, indent: str = "") -> str:
    """
    Arrow-key single-select picker.
    Falls back to plain input on non-TTY or when items is empty.
    """
    import tty, termios

    if not sys.stdin.isatty() or not items:
        return input(f"{indent}{prompt}: ").strip()

    selected = default_idx
    first_render = True

    def _render(idx: int) -> None:
        nonlocal first_render
        if not first_render:
            sys.stdout.write(f"\033[{len(items)}A")
        first_render = False
        for i, name in enumerate(items):
            if i == idx:
                sys.stdout.write(f"\r{indent} {BOLD_CYAN}> {name}{RESET}\033[K\n")
            else:
                sys.stdout.write(f"\r{indent}   {name}\033[K\n")
        sys.stdout.flush()

    print(f"{indent}{prompt} (↑↓ to move, Enter to confirm):")
    _render(selected)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                if ch2 == "[":
                    if ch3 == "A" and selected > 0:
                        selected -= 1
                    elif ch3 == "B" and selected < len(items) - 1:
                        selected += 1
            _render(selected)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print()
    return items[selected]


def pick_many(
    prompt: str,
    items: list[str],
    defaults: list[bool],
    indent: str = "",
) -> list[bool]:
    """
    Arrow-key multi-select picker (Space to toggle, Enter to confirm).
    Returns list of bool parallel to items.
    Falls back to defaults on non-TTY.
    """
    import tty, termios

    if not sys.stdin.isatty() or not items:
        return list(defaults)

    states = list(defaults)
    selected = 0
    first_render = True

    def _render(idx: int) -> None:
        nonlocal first_render
        if not first_render:
            sys.stdout.write(f"\033[{len(items)}A")
        first_render = False
        for i, name in enumerate(items):
            mark = "[x]" if states[i] else "[ ]"
            if i == idx:
                sys.stdout.write(f"\r{indent} {BOLD_CYAN}> {mark} {name}{RESET}\033[K\n")
            else:
                sys.stdout.write(f"\r{indent}   {mark} {name}\033[K\n")
        sys.stdout.flush()

    print(f"{indent}{prompt} (↑↓ to move, Space to toggle, Enter to confirm):")
    _render(selected)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == " ":
                states[selected] = not states[selected]
            elif ch in ("\r", "\n"):
                break
            elif ch == "\x03":
                raise KeyboardInterrupt
            elif ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                if ch2 == "[":
                    if ch3 == "A" and selected > 0:
                        selected -= 1
                    elif ch3 == "B" and selected < len(items) - 1:
                        selected += 1
            _render(selected)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print()
    return states
