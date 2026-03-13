"""Session UI interface — FCP-Core display layer.

PlainUI: ANSI rendering, zero external dependencies (default for ./fcp).
RichUI:  full Rich rendering, imported lazily from core.tui (used by ./fcp tui).
"""

from __future__ import annotations

import re
import sys


# ---------------------------------------------------------------------------
# ANSI helpers (used by PlainUI only)
# ---------------------------------------------------------------------------

_TTY = sys.stdout.isatty()


def _A(code: str) -> str:
    return f"\033[{code}m" if _TTY else ""


_RST   = _A("0")
_BOLD  = _A("1")
_DIM   = _A("2")
_ITA   = _A("3")
_RED   = _A("31")
_GRN   = _A("32")
_YLW   = _A("33")
_CYAN  = _A("36")
_C1    = _A("1;36")   # bold cyan  — H1
_C2    = _A("1;34")   # bold blue  — H2
_C3    = _A("1")      # bold       — H3
_ICODE = _A("97;40")  # white/black bg — inline code

# Strip remaining fenced blocks before plain-text display.
# RichUI skips this and renders code blocks natively.
_CODE_BLOCK_RE = re.compile(r"```[\w-]*\n.*?\n```", re.DOTALL)


def _render_md(text: str) -> str:
    """Convert basic markdown to ANSI escape codes."""
    lines: list[str] = []
    in_fence = False

    for raw_line in text.splitlines():
        if raw_line.strip().startswith("```"):
            in_fence = not in_fence
            lines.append(_DIM + "  " + "\u2504" * 20 + _RST)
            continue

        if in_fence:
            lines.append(f"  {_DIM}{raw_line}{_RST}")
            continue

        line = raw_line

        # Headings
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            lvl = len(m.group(1))
            colour = [_C1, _C2, _C3][lvl - 1]
            lines.append(colour + m.group(2) + _RST)
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}\s*$", line):
            lines.append(_DIM + "\u2500" * 48 + _RST)
            continue

        # Bullet and numbered lists
        bm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)", line)
        if bm:
            indent, marker, body = bm.group(1), bm.group(2), bm.group(3)
            glyph = "\u25e6" if len(indent) >= 2 else "\u2022"
            if re.match(r"\d+\.", marker):
                glyph = marker
            line = f"{indent}{glyph} {body}"

        # Inline: **bold**, *italic*, `code`
        line = re.sub(r"\*\*(.+?)\*\*", _BOLD + r"\1" + _RST, line)
        line = re.sub(r"\*(.+?)\*",     _ITA  + r"\1" + _RST, line)
        line = re.sub(r"`([^`]+)`",     _ICODE + r"\1" + _RST, line)

        lines.append(line)

    if in_fence:
        lines.append(_DIM + "  " + "\u2504" * 20 + _RST)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UI base interface
# ---------------------------------------------------------------------------

class UI:
    """Base display interface.  All methods are no-ops; subclasses override."""

    verbose: bool = False

    def session_start(self, session_id: str) -> None: ...
    def write_prompt(self) -> None: ...
    def narrative(self, text: str) -> None: ...
    def info(self, text: str) -> None: ...
    def warning(self, text: str) -> None: ...
    def error(self, text: str) -> None: ...
    def verbose_cycle(self, cycle: int, turns: int, tokens: int) -> None: ...
    def verbose_text(self, label: str, text: str) -> None: ...
    def skill_ok(self, skill: str, output: str) -> None: ...
    def skill_err(self, skill: str, error: str) -> None: ...
    def help_start(self) -> None: ...
    def help_item(self, alias: str, desc: str) -> None: ...
    def help_end(self) -> None: ...
    def teardown(self, phase: str) -> None: ...
    def session_close(self, by: str) -> None: ...


# ---------------------------------------------------------------------------
# PlainUI — ANSI rendering, zero external deps
# ---------------------------------------------------------------------------

_CLOSE_MSGS = {
    "entity":   "Session closed by entity.",
    "operator": "Session closed by Operator.",
    "budget":   "Context budget critical — session closed by SIL.",
}


class PlainUI(UI):
    """Plain terminal UI: ANSI markdown rendering, no external dependencies."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def session_start(self, session_id: str) -> None:
        print(f"\n  {_DIM}Session {session_id[:8]}…{_RST}  "
              "Type your message or /help.\n")

    def write_prompt(self) -> None:
        sys.stdout.write(f"{_BOLD}you>{_RST} ")
        sys.stdout.flush()

    def narrative(self, text: str) -> None:
        text = _CODE_BLOCK_RE.sub("", text).strip()
        if not text:
            return
        rendered = _render_md(text)
        indented  = "\n".join("  " + ln for ln in rendered.splitlines())
        print(f"\n{_CYAN}fcp>{_RST}\n{indented}\n")

    def info(self, text: str) -> None:
        print(f"  {_DIM}{text}{_RST}")

    def warning(self, text: str) -> None:
        print(f"  {_YLW}⚠{_RST}  {text}")

    def error(self, text: str) -> None:
        print(f"\n  {_RED}{_BOLD}✖{_RST}  {text}\n")

    def verbose_cycle(self, cycle: int, turns: int, tokens: int) -> None:
        if self.verbose:
            print(f"\n  {_DIM}[VRB] cycle={cycle}  turns={turns}  "
                  f"~{tokens} tokens{_RST}")

    def verbose_text(self, label: str, text: str) -> None:
        if self.verbose:
            indented = "\n".join("    " + ln for ln in text.splitlines())
            print(f"  {_DIM}[VRB] {label}:{_RST}\n{_DIM}{indented}{_RST}\n")

    def skill_ok(self, skill: str, output: str) -> None:
        print(f"\n  {_GRN}✓{_RST} {_BOLD}{skill}{_RST}  {output}\n")

    def skill_err(self, skill: str, error: str) -> None:
        print(f"\n  {_RED}✗{_RST} {_BOLD}{skill}{_RST}  {error}\n")

    def help_start(self) -> None:
        print("\n  Slash commands:")

    def help_item(self, alias: str, desc: str) -> None:
        print(f"    {_CYAN}{alias:<20}{_RST} {_DIM}{desc}{_RST}")

    def help_end(self) -> None:
        print()

    def teardown(self, phase: str) -> None:
        print(f"  {_DIM}{phase}{_RST}")

    def session_close(self, by: str) -> None:
        msg = _CLOSE_MSGS.get(by, "Session closed.")
        print(f"\n  {_DIM}{msg}{_RST}\n")
