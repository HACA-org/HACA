"""RichUI — full Rich terminal rendering for ./fcp tui.

Requires the `rich` package:
    uv pip install rich
"""

from __future__ import annotations

import sys

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text
except ImportError as _e:
    raise ImportError(
        "The 'tui' subcommand requires the 'rich' package.\n"
        "Install it with:  uv pip install rich"
    ) from _e

from .ui import UI, _CODE_BLOCK_RE, _CLOSE_MSGS

_console = Console()


class RichUI(UI):
    """Rich-based terminal UI for ./fcp tui."""

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose

    def session_start(self, session_id: str) -> None:
        _console.print()
        _console.print(Panel(
            Text.from_markup(
                f"[bold cyan]Session[/bold cyan] [dim]{session_id[:8]}…[/dim]"
                "  Type your message or [bold]/help[/bold]"
            ),
            border_style="dim cyan",
            expand=False,
        ))
        _console.print()

    def write_prompt(self) -> None:
        # Use raw write so readline still works correctly
        sys.stdout.write("\033[1myou>\033[0m ")
        sys.stdout.flush()

    def narrative(self, text: str) -> None:
        # Rich Markdown renders code blocks natively — no stripping needed
        text = text.strip()
        if not text:
            return
        _console.print(Rule(style="dim cyan"))
        _console.print(Markdown(text))
        _console.print(Rule(style="dim cyan"))
        _console.print()

    def info(self, text: str) -> None:
        _console.print(f"  [dim]{text}[/dim]")

    def warning(self, text: str) -> None:
        _console.print(f"  [bold yellow]⚠[/bold yellow]  {text}")

    def error(self, text: str) -> None:
        _console.print()
        _console.print(f"  [bold red]✖[/bold red]  [red]{text}[/red]")
        _console.print()

    def verbose_cycle(self, cycle: int, turns: int, tokens: int) -> None:
        if self.verbose:
            _console.print(
                f"\n  [dim]▸ cycle={cycle}  turns={turns}  ~{tokens} tokens[/dim]"
            )

    def verbose_text(self, label: str, text: str) -> None:
        if self.verbose:
            _console.print(Panel(
                text[:1200],
                title=f"[dim]{label}[/dim]",
                border_style="dim",
                expand=False,
            ))

    def skill_ok(self, skill: str, output: str) -> None:
        _console.print(
            f"\n  [bold green]✓[/bold green] [bold]{skill}[/bold]  {output}\n"
        )

    def skill_err(self, skill: str, error: str) -> None:
        _console.print(
            f"\n  [bold red]✗[/bold red] [bold]{skill}[/bold]  {error}\n"
        )

    def help_start(self) -> None:
        _console.print()
        _console.print("  [bold]Slash commands:[/bold]")

    def help_item(self, alias: str, desc: str) -> None:
        _console.print(
            f"    [cyan]{alias:<20}[/cyan] [dim]{desc}[/dim]"
        )

    def help_end(self) -> None:
        _console.print()

    def teardown(self, phase: str) -> None:
        _console.print(f"  [dim]{phase}[/dim]")

    def session_close(self, by: str) -> None:
        msg = _CLOSE_MSGS.get(by, "Session closed.")
        _console.print(f"\n  [dim italic]{msg}[/dim italic]\n")
