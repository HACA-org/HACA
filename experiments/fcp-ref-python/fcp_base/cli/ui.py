"""
CLI boot header and display helpers.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from ..store import load_baseline, read_json
from .. import ui as _ui

if TYPE_CHECKING:
    from ..store import Layout

_log = logging.getLogger(__name__)


def build_boot_stats(
    layout: "Layout",
    index: dict,
    system: str,
    chat_history: list,
    tools: list,
) -> dict:
    """Collect stats for the boot header.  Scans integrity.log once."""
    total_chars = len(system) + sum(len(str(m.get("content", ""))) for m in chat_history)
    total_tokens = total_chars // 4
    baseline = load_baseline(layout)
    ctx_window = baseline.get("context_window", {}).get("budget_pct", 0)
    ctx_pct = round(total_tokens / ctx_window * 100, 1) if ctx_window else None

    sessions = 0
    evolutions_auth = 0
    evolutions_total = 0
    if layout.integrity_log.exists():
        for line in layout.integrity_log.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                raw = rec.get("data", "{}")
                d = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(d, dict):
                    continue
                t = d.get("type")
                if t == "SLEEP_COMPLETE":
                    sessions += 1
                elif t == "EVOLUTION_AUTH":
                    evolutions_total += 1
                    evolutions_auth += 1
                elif t == "ENDURE_COMMIT":
                    evolutions_total += 1
            except json.JSONDecodeError:
                pass
            except Exception as e:
                _log.debug("integrity log parse error: %s", e)

    cycles = 0
    if layout.integrity_chain.exists():
        for line in layout.integrity_chain.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                if rec.get("type") == "ENDURE_COMMIT":
                    cycles += 1
            except json.JSONDecodeError:
                pass
            except Exception as e:
                _log.debug("integrity chain parse error: %s", e)

    memories = 0
    for d in (layout.episodic_dir, layout.semantic_dir):
        if d.exists():
            memories += sum(1 for f in d.rglob("*") if f.is_file())

    n_notif = 0
    if layout.operator_notifications_dir.exists():
        n_notif = sum(
            1 for f in layout.operator_notifications_dir.iterdir()
            if f.suffix == ".json" and not f.name.endswith(".tmp")
        )

    return {
        "ctx_tokens": total_tokens,
        "ctx_pct": ctx_pct,
        "sessions": sessions,
        "cycles": cycles,
        "memories": memories,
        "evolutions_auth": evolutions_auth,
        "evolutions_total": evolutions_total,
        "skills": len(index.get("skills", [])),
        "tools": len(tools),
        "notifications": n_notif,
    }


def print_block(label: str, lines: list, color: str = "\x1b[96m") -> None:
    """Print a bordered block with a colored header label and closing border."""
    width = _ui._W
    border = "─" * (width - len(label) - 3)
    print(f"{color}╭─ {label} {border}╮{_ui.RESET}")
    for line in lines:
        print(f"{_ui.DIM}│{_ui.RESET} {line}")
    print(f"{color}╰{'─' * width}╯{_ui.RESET}")


def print_boot_header(layout: "Layout", index: dict) -> None:
    from ..session import build_boot_context
    from ..tools import build_tool_declarations as _tool_declarations

    system, chat_history = build_boot_context(layout, index)
    tools = _tool_declarations(layout, index)
    s = build_boot_stats(layout, index, system, chat_history, tools)

    ctx_str = f"{s['ctx_pct']}%" if s["ctx_pct"] is not None else "?%"
    evol_str = f"{s['evolutions_auth']}/{s['evolutions_total']}"

    try:
        baseline = read_json(layout.baseline)
        cpe_cfg = baseline.get("cpe", {})
        model_str = f"{cpe_cfg.get('backend', '?')}:{cpe_cfg.get('model', '?')}"
    except Exception:
        model_str = "?"

    header_lines = [
        f"{model_str} | tools: {s['tools']}",
        f"boot: {ctx_str} ctx | sessions: {s['sessions']} | cycles: {s['cycles']}",
        f"memories: {s['memories']} | evolutions: {evol_str} | skills: {s['skills']}",
    ]
    print_block("FCP", header_lines, color="\x1b[90m")
    notif_str = f" You have {s['notifications']} new notifications in /inbox." if s["notifications"] else ""
    print(f"Type your message or /help.{notif_str}")
