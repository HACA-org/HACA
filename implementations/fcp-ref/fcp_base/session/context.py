"""
Boot context assembly — system prompt + initial chat history (FCP §5.1).
"""

from __future__ import annotations

import json
from typing import Any

from ..mil import SESSION_CACHE_FILE
from ..store import Layout, read_json, read_jsonl
from ..tools import build_tools_index as _build_tools_index
from .. import cmi_fmt as _cmi_fmt
from .vlog import _vlog

_SYSTEM_TYPES = _cmi_fmt.SYSTEM_TYPES


def build_boot_context(
    layout: Layout,
    index: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Build the fixed system prompt and initial chat history (session tail).

    Called once at session start.  Returns:
      system       — persona + boot protocol + skills + memory (never changes)
      chat_history — tail of session.jsonl reconstructed as message dicts

    Each cognitive cycle appends only the new stimulus to chat_history.
    """
    # --- system prompt: [IDENTITY] = persona + imprint line ---
    persona_parts: list[str] = []
    if layout.persona_dir.exists():
        for p in sorted(layout.persona_dir.iterdir()):
            if p.is_file():
                persona_parts.append(p.read_text(encoding="utf-8").strip())
    persona_text = "\n\n".join(persona_parts) if persona_parts else "You are a helpful assistant."

    imprint_line = ""
    imprint_path = layout.root / "memory" / "imprint.json"
    if imprint_path.exists():
        try:
            imp = json.loads(imprint_path.read_text(encoding="utf-8"))
            ob = imp.get("operator_bound", {})
            activated = imp.get("activated_at", "")
            profile = imp.get("haca_profile", "")
            op_name = ob.get("operator_name", "")
            op_email = ob.get("operator_email", "")
            op_str = f"{op_name} <{op_email}>" if op_email else op_name
            imprint_line = f"Activated: {activated} | Profile: {profile} | Operator: {op_str}"
        except Exception:
            pass

    identity_parts = ["[IDENTITY]", persona_text]
    if imprint_line:
        identity_parts.append(imprint_line)
    system_persona = "\n\n".join(identity_parts)

    # --- instruction block: boot protocol + memory + skills ---
    boot_protocol = ""
    if layout.boot_md.exists():
        boot_protocol = layout.boot_md.read_text(encoding="utf-8").strip()

    memory_parts: list[str] = []
    if layout.working_memory.exists():
        wm = read_json(layout.working_memory)
        for entry in sorted(wm.get("entries", []), key=lambda e: int(e.get("priority", 99))):
            rel = entry.get("path", "")
            if not rel:
                continue
            p = layout.root / rel
            if p.is_file():
                memory_parts.append(p.read_text(encoding="utf-8").strip())

    tools_index = _build_tools_index(layout, index)

    instruction_parts: list[str] = [boot_protocol, tools_index]
    if memory_parts:
        instruction_parts.append("## Active Memory\n\n" + "\n\n---\n\n".join(memory_parts))

    instruction_block = "\n\n".join(instruction_parts)

    # system = persona; instruction block is the first user/assistant exchange
    system = system_persona

    # --- presession ---
    presession_lines: list[str] = []
    if layout.presession_dir.exists():
        for f in sorted(layout.presession_dir.iterdir()):
            if f.suffix == ".json":
                try:
                    presession_lines.append(f.read_text(encoding="utf-8").strip())
                except UnicodeDecodeError as e:
                    _vlog("fcp", f"presession file {f.name} has encoding error: {e}")
                except OSError as e:
                    _vlog("fcp", f"presession file {f.name} cannot be read: {e}")
                except Exception as e:
                    _vlog("fcp", f"presession file {f.name} error: {e}")

    # --- initial chat history: instruction block + session tail ---
    chat_history: list[dict[str, Any]] = [
        {"role": "user", "content": instruction_block},
        {"role": "assistant", "content": "Understood. I am ready."},
    ]

    if presession_lines:
        pre_text = "[Pre-session context]\n" + "\n".join(presession_lines)
        chat_history.append({"role": "user", "content": pre_text})
        chat_history.append({"role": "assistant", "content": "Noted."})

    # Reconstruct session tail as conversation turns
    for role, text in _session_to_turns(layout):
        chat_history.append({"role": role, "content": text})

    return system, chat_history


def _session_to_turns(layout: Layout) -> list[tuple[str, str]]:
    """Convert session.jsonl into (role, text) pairs for chat history.

    Uses cached session tail from .session-cache.json (after sleep) for
    faster boots. Cache is refreshed on every sleep cycle.
    """
    # Try to load cached session tail (populated after each sleep)
    cache_file = layout.root / "memory" / SESSION_CACHE_FILE
    if cache_file.exists():
        try:
            cache = read_json(cache_file)
            cached_turns = cache.get("turns", [])
            # Convert back to list of tuples
            pairs = [(turn["role"], turn["content"]) for turn in cached_turns]
            return pairs
        except json.JSONDecodeError as e:
            _vlog("fcp", f"session cache corrupted ({e}) — performing full scan")
        except (KeyError, TypeError) as e:
            _vlog("fcp", f"session cache schema error ({e}) — performing full scan")
        except Exception as e:
            _vlog("fcp", f"session cache error ({e}) — performing full scan")

    # Full scan if no cache (cold boot)
    pairs: list[tuple[str, str]] = []

    for env in read_jsonl(layout.session_store):
        actor = str(env.get("actor", env.get("source", "")))
        raw_data = env.get("data", "")

        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                # Not JSON — treat as raw string data
                data = raw_data
            except Exception as e:
                _vlog("fcp", f"envelope data parse error ({e}) — using raw data")
                data = raw_data
        else:
            data = raw_data

        # filter system envelopes
        if isinstance(data, dict) and data.get("type") in _SYSTEM_TYPES:
            continue

        if actor in ("operator", "user"):
            role = "user"
        elif actor in ("cpe", "assistant"):
            role = "assistant"
        else:
            role = "user"

        if isinstance(data, str):
            text = data.strip()
        elif isinstance(data, dict):
            if "tool_result" in data:
                tr = data["tool_result"]
                text = f"[tool result: {tr.get('tool', '?')}]\n{json.dumps(tr.get('content', ''), ensure_ascii=False)}"
            else:
                text = json.dumps(data, ensure_ascii=False)
        else:
            text = json.dumps(data, ensure_ascii=False)

        if not text:
            continue

        # merge consecutive same-role entries
        if pairs and pairs[-1][0] == role:
            prev_role, prev_text = pairs[-1]
            pairs[-1] = (prev_role, prev_text + "\n\n" + text)
        else:
            pairs.append((role, text))

    return pairs


def _rebuild_compact_history(
    layout: Layout,
    index: dict[str, Any],
    system: str,
) -> list[dict[str, Any]]:
    """Rebuild a minimal chat_history after session compaction.

    Structure:
      [0] user  — instruction block (boot protocol + skills)
      [1] asst  — "Understood. I am ready."
      [2] user  — working memory entries (freshly loaded from disk)
      [3] asst  — "Noted."
      [4] user  — [session compacted] + consolidation + handoff
      [5] asst  — ""  (placeholder for next CPE turn)
    """
    # Re-use build_boot_context to get fresh instruction block + working memory
    _, base_history = build_boot_context(layout, index)
    # base_history = [instruction_block, ack, (optional presession), ...]
    # We want only the first two (instruction block + ack) as the clean base.
    new_history: list[dict[str, Any]] = list(base_history[:2])

    # Load fresh working memory entries as context
    wm_parts: list[str] = []
    if layout.working_memory.exists():
        wm = read_json(layout.working_memory)
        for entry in sorted(wm.get("entries", []), key=lambda e: int(e.get("priority", 99))):
            p = layout.root / entry.get("path", "")
            if p.exists():
                wm_parts.append(p.read_text(encoding="utf-8").strip())
    if wm_parts:
        new_history.append({"role": "user", "content": "## Working Memory\n\n" + "\n\n---\n\n".join(wm_parts)})
        new_history.append({"role": "assistant", "content": "Noted."})

    # Load consolidation + handoff from session_handoff.json
    compact_parts: list[str] = ["[session compacted]"]
    if layout.session_handoff.exists():
        try:
            handoff = read_json(layout.session_handoff)
            if handoff.get("pending_tasks"):
                compact_parts.append("Pending tasks:\n" + "\n".join(f"- {t}" for t in handoff["pending_tasks"]))
            if handoff.get("next_steps"):
                compact_parts.append(f"Next steps: {handoff['next_steps']}")
        except json.JSONDecodeError as e:
            _vlog("fcp", f"session handoff corrupted ({e}) — skipping")
        except (KeyError, TypeError) as e:
            _vlog("fcp", f"session handoff schema error ({e}) — skipping")
        except Exception as e:
            _vlog("fcp", f"session handoff load error ({e}) — skipping")
    new_history.append({"role": "user", "content": "\n\n".join(compact_parts)})
    new_history.append({"role": "assistant", "content": ""})

    return new_history
