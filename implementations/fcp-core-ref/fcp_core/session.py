"""
Session loop — FCP-Core §6.

Drives the cognitive cycle:
  drain io/inbox/ → consolidate → invoke CPE with growing chat_history
  → process tool_use → return tool_results → repeat

Context is assembled once at session start (system prompt + initial history from
session tail). Each cycle appends only the new stimulus to the in-memory
chat_history — the CPE never re-receives the boot manifest.

Session ends on session_close signal (CPE, SIL, or Operator).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .acp import drain_inbox, make as acp_encode
from .cpe.base import AdapterRef, CPEAdapter, CPEResponse
from .mil import memory_recall, process_closure, result_recall, summarize_session, write_episodic
from .operator import is_verbose as _is_verbose, get_debugger as _get_debugger, is_compact_pending as _is_compact_pending, set_compact_pending as _set_compact_pending
from .store import Layout, append_jsonl, atomic_write, read_json, read_jsonl
from . import vital as _vital


# ---------------------------------------------------------------------------
# Main session loop
# ---------------------------------------------------------------------------

def run_session(
    layout: Layout,
    adapter: CPEAdapter | AdapterRef,
    index: dict[str, Any],
    *,
    inject: list[dict[str, Any]] | None = None,
    greeting: bool = False,
) -> str:
    """Run the cognitive session loop until session close.

    inject:   optional list of ACP envelopes to prepend as first stimuli.
    greeting: if True, inject a SESSION_START stimulus so the CPE wakes and greets.
    Returns the close reason string.
    """
    tools = _tool_declarations()
    adapter_ref = adapter if isinstance(adapter, AdapterRef) else AdapterRef(adapter)

    # --- Build system prompt and initial chat history once at session start ---
    system, chat_history = build_boot_context(layout, index)
    _vlog("fcp", f"boot context: system={len(system)} chars, history={len(chat_history)} msgs")

    # Inject greeting stimulus as first user message
    if greeting:
        msg = "Session started. Greet the Operator and await input."
        env = acp_encode(env_type="MSG", source="fcp",
                         data={"type": "SESSION_START", "msg": msg})
        append_jsonl(layout.session_store, env)
        chat_history.append({"role": "user", "content": msg})
        _vlog("fcp", "SESSION_START stimulus injected")

    if inject:
        for env in inject:
            append_jsonl(layout.session_store, env)
            text = _envelope_to_text(env)
            if text:
                chat_history.append({"role": "user", "content": text})

    close_reason = "session_close"
    cycle = 0
    compact_in_progress = False
    stimulus_ready = bool(greeting or inject)
    tokens_used = 0

    # Vital Check state — triggers on cycle_threshold or interval_seconds
    _baseline = None
    _vital_state = None
    try:
        from .formats import StructuralBaseline
        _baseline = StructuralBaseline.from_dict(read_json(layout.baseline))
        _session_id = ""
        if layout.session_token.exists():
            _session_id = str(read_json(layout.session_token).get("session_id", ""))
        _vital_state = _vital.VitalCheckState(session_id=_session_id)
    except Exception:
        pass  # no baseline — vital check disabled

    while True:
        # drain io/inbox/ → consolidate to session.jsonl
        inbox_envs = _drain_and_consolidate(layout)
        for env in inbox_envs:
            text = _envelope_to_text(env)
            if text:
                chat_history.append({"role": "user", "content": text})
                stimulus_ready = True

        # if no stimulus, wait for operator input before invoking CPE
        if not stimulus_ready:
            try:
                user_input = _readline_with_history("> ")
            except KeyboardInterrupt:
                print()
                close_reason = "operator_interrupt"
                break
            except EOFError:
                close_reason = "operator_eof"
                break
            stripped = user_input.strip()
            if not stripped:
                continue
            # platform commands — handle without invoking CPE
            if stripped.startswith("/"):
                from .operator import handle_platform_command
                handled = handle_platform_command(layout, stripped, adapter_ref=adapter_ref)
                if handled:
                    if stripped.lower().split()[0] in ("/exit", "/bye", "/close"):
                        close_reason = "operator_exit"
                        break
                    if stripped.lower().split()[0] in ("/new", "/clear", "/reset"):
                        close_reason = "operator_reset"
                        break
                    # check if /compact was just requested
                    if _is_compact_pending():
                        _set_compact_pending(False)
                        compact_in_progress = True
                        compact_msg = (
                            "[COMPACT_REQUEST] The operator has requested session compaction. "
                            "Generate a closure_payload now via fcp_mil to preserve your working context. "
                            "The session will continue after compaction — use session_handoff.next_steps "
                            "to describe where to resume."
                        )
                        _append_msg(layout, "fcp", compact_msg)
                        chat_history.append({"role": "user", "content": compact_msg})
                        stimulus_ready = True
                    continue  # back to top — wait for next input, no CPE call
            _vlog("operator", f"input: {stripped!r}")
            _append_msg(layout, "operator", user_input)
            chat_history.append({"role": "user", "content": stripped})

        stimulus_ready = False
        cycle += 1
        _vlog("fcp", f"── Cognitive Cycle {cycle} ──────────────────────────")
        _vlog_request(system, chat_history, tools)

        # invoke CPE (adapter_ref.current may be swapped mid-session via /model)
        response = adapter_ref.current.invoke(system, chat_history, tools)
        _vlog_response(response)
        tokens_used += response.input_tokens + response.output_tokens

        # add CPE response to chat history
        if response.text:
            _append_msg(layout, "cpe", response.text)
            print(response.text)
            chat_history.append({"role": "assistant", "content": response.text})
        elif response.tool_use_calls:
            # assistant turn with tool use (no text) — still needs to be tracked
            chat_history.append({"role": "assistant", "content": ""})

        # process tool_use calls — fcp_mil before fcp_exec before fcp_sil (per spec)
        tool_calls = sorted(
            response.tool_use_calls,
            key=lambda c: 0 if c.tool == "fcp_mil" else (1 if c.tool == "fcp_exec" else 2),
        )

        session_closed = False
        tool_summaries: list[str] = []
        for call in tool_calls:
            _vlog("fcp", f"dispatch → {call.tool}")
            _vlog_json(f"fcp→{call.tool}", call.input)
            result, closed = dispatch_tool_use(layout, call, index)
            _vlog_json(f"{call.tool}→fcp", result)
            ts = _return_tool_result(layout, call.id, call.tool, result)
            status = "error" if "error" in result else "ok"
            action = call.input.get("type", call.tool) if isinstance(call.input, dict) else call.tool
            tool_summaries.append(f"[{call.tool}:{action} ts:{ts} — {status}]")
            if closed:
                close_reason = "session_close"
                session_closed = True

        # tool results go into chat history as compact summaries.
        # use result_recall to retrieve the full payload if needed.
        if tool_summaries:
            chat_history.append({"role": "user", "content": "\n".join(tool_summaries)})
            stimulus_ready = True  # tool results need a follow-up CPE cycle

        if session_closed:
            break

        # Vital Check — tick counter; run if either trigger threshold is reached
        if _vital_state is not None and _baseline is not None:
            _vital.tick(_vital_state)
            if _vital.should_run(_vital_state, _baseline):
                _vital.run(layout, _baseline, _vital_state, tokens_used)

        # compact: if closure_payload was written during this cycle, execute Stage 1
        # and rebuild chat_history with the condensed context
        if compact_in_progress and layout.pending_closure.exists():
            compact_in_progress = False
            _vlog("fcp", "compact: processing closure payload")
            process_closure(layout)
            chat_history[:] = _rebuild_compact_history(layout, index, system)
            summarize_session(layout)
            _vlog("fcp", f"compact: done — history={len(chat_history)} msgs")
            print("  [session compacted]")

    _vlog("fcp", f"session closed — reason: {close_reason}")
    return close_reason


# ---------------------------------------------------------------------------
# Boot context assembly  §5.1
# ---------------------------------------------------------------------------

# System envelope types that must not appear as conversation turns.
_SYSTEM_TYPES = frozenset({
    "SESSION_START", "SESSION_CLOSE", "SLEEP_COMPLETE", "HEARTBEAT",
    "DRIFT_FAULT", "IDENTITY_DRIFT", "SEVERANCE_PENDING", "CRITICAL_CLEARED",
    "PROPOSAL_PENDING", "EVOLUTION_AUTH", "EVOLUTION_REJECTED",
    "ENDURE_COMMIT", "DECOMMISSION",
})


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
    # --- system prompt: persona ---
    persona_parts: list[str] = []
    if layout.persona_dir.exists():
        for p in sorted(layout.persona_dir.iterdir()):
            if p.is_file():
                persona_parts.append(p.read_text(encoding="utf-8").strip())
    system_persona = "\n\n".join(persona_parts) if persona_parts else "You are a helpful assistant."

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

    skill_blocks: list[str] = []
    if layout.skills_index.exists():
        idx = read_json(layout.skills_index)
        visible = [s for s in idx.get("skills", []) if s.get("class") != "operator"]
        for skill in visible:
            mrel = skill.get("manifest", "")
            if mrel:
                mpath = layout.root / mrel
                if mpath.exists():
                    m = read_json(mpath)
                    block = {k: m[k] for k in (
                        "name", "version", "description",
                        "timeout_seconds", "permissions",
                    ) if k in m}
                    skill_blocks.append(
                        f"[SKILL:{skill['name']}]\n{json.dumps(block, indent=2)}"
                    )

    instruction_parts: list[str] = [boot_protocol]
    if memory_parts:
        instruction_parts.append("## Active Memory\n\n" + "\n\n---\n\n".join(memory_parts))
    if skill_blocks:
        instruction_parts.append("## Available Skills\n\n" + "\n\n".join(skill_blocks))

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
                except Exception:
                    pass

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
    """Convert session.jsonl into (role, text) pairs for chat history."""
    pairs: list[tuple[str, str]] = []

    for env in read_jsonl(layout.session_store):
        actor = str(env.get("actor", env.get("source", "")))
        raw_data = env.get("data", "")

        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except Exception:
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


def _envelope_to_text(env: dict[str, Any]) -> str:
    """Extract displayable text from an ACP envelope for chat history injection."""
    raw_data = env.get("data", "")
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except Exception:
            data = raw_data
    else:
        data = raw_data

    if isinstance(data, dict):
        if data.get("type") in _SYSTEM_TYPES:
            return ""
        return json.dumps(data, ensure_ascii=False)
    if isinstance(data, str):
        return data.strip()
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool dispatch  §6.2
# ---------------------------------------------------------------------------

def dispatch_tool_use(
    layout: Layout,
    call: Any,
    index: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Dispatch a single tool_use call. Returns (result_dict, session_closed)."""
    tool = call.tool
    inp = call.input if isinstance(call.input, dict) else {}

    # Some models (e.g. Ollama/llama) wrap the action as a JSON string under "action".
    if "action" in inp and isinstance(inp["action"], str) and len(inp) == 1:
        try:
            inp = json.loads(inp["action"])
        except Exception:
            pass

    if tool == "fcp_mil":
        return _dispatch_mil(layout, inp)
    if tool == "fcp_exec":
        return _dispatch_exec(layout, inp, index)
    if tool == "fcp_sil":
        return _dispatch_sil(layout, inp)
    return {"error": f"unknown tool: {tool}"}, False


def _dispatch_mil(
    layout: Layout, inp: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "memory_recall":
            result = memory_recall(layout, str(action.get("query", "")),
                                   str(action.get("path", "")))
            results.append({"type": "memory_recall", "result": result})
        elif atype == "result_recall":
            ts = int(action.get("ts", 0))
            result = result_recall(layout, ts)
            results.append({"type": "result_recall", "result": result})
        elif atype == "memory_write":
            slug = str(action.get("slug", "")).strip()
            content = str(action.get("content", ""))
            if slug:
                write_episodic(layout, slug, content)
            results.append({"type": "memory_write", "status": "ok"})
        elif atype == "closure_payload":
            atomic_write(layout.pending_closure, dict(action))
            results.append({"type": "closure_payload", "status": "acknowledged"})
        else:
            results.append({"type": atype, "error": "unknown mil action"})
    return {"results": results}, False


def _dispatch_exec(
    layout: Layout,
    inp: dict[str, Any],
    index: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    from .exec_ import dispatch, ExecError, SkillRejected
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "skill_request":
            skill_name = str(action.get("skill", ""))
            params = action.get("params", {})
            # Some models serialize params as a JSON string instead of an object.
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except Exception:
                    params = {}
            if not isinstance(params, dict):
                params = {}
            try:
                output = dispatch(layout, skill_name, params, index)
                results.append({"type": "skill_request", "skill": skill_name,
                                 "status": "dispatched", "output": output})
            except (SkillRejected, ExecError) as exc:
                results.append({"type": "skill_request", "skill": skill_name,
                                 "error": str(exc)})
        elif atype == "skill_info":
            skill_name = str(action.get("skill", ""))
            results.append(_skill_info(layout, skill_name, index))
        else:
            results.append({"type": atype, "error": "unknown exec action"})
    return {"results": results}, False


def _dispatch_sil(
    layout: Layout, inp: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    session_closed = False
    for action in actions:
        atype = action.get("type", "")
        if atype == "evolution_proposal":
            _stage_evolution_proposal(layout, str(action.get("content", "")))
            results.append({"type": "evolution_proposal", "status": "queued"})
        elif atype == "session_close":
            session_closed = True
            results.append({"type": "session_close", "status": "acknowledged"})
        else:
            results.append({"type": atype, "error": "unknown sil action"})
    return {"results": results}, session_closed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill_info(
    layout: Layout, skill_name: str, index: dict[str, Any]
) -> dict[str, Any]:
    """Return the markdown content of a skill's manifest, or an error."""
    for entry in index.get("skills", []):
        if entry.get("name") == skill_name:
            rel = entry.get("manifest", "")
            if rel:
                mpath = layout.root / rel
                # look for a README.md next to the manifest
                readme = mpath.parent / "README.md"
                if readme.exists():
                    return {"type": "skill_info", "skill": skill_name,
                            "content": readme.read_text(encoding="utf-8")}
                # fall back to the manifest JSON itself
                if mpath.exists():
                    return {"type": "skill_info", "skill": skill_name,
                            "content": mpath.read_text(encoding="utf-8")}
            return {"type": "skill_info", "skill": skill_name, "error": "no manifest path"}
    return {"type": "skill_info", "skill": skill_name, "error": "skill not in index"}


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
        except Exception:
            pass
    new_history.append({"role": "user", "content": "\n\n".join(compact_parts)})
    new_history.append({"role": "assistant", "content": ""})

    return new_history


def _drain_and_consolidate(layout: Layout) -> list[dict[str, Any]]:
    envelopes = drain_inbox(layout.inbox_dir)
    for env in envelopes:
        append_jsonl(layout.session_store, env)
    return envelopes


def _append_msg(layout: Layout, source: str, text: str) -> None:
    envelope = acp_encode(env_type="MSG", source=source, data=text)
    append_jsonl(layout.session_store, envelope)


def _return_tool_result(
    layout: Layout, call_id: str, tool: str, result: dict[str, Any]
) -> int:
    """Write tool result to session.jsonl and return its numeric timestamp (ms)."""
    import time as _time
    ts_ms = int(_time.time() * 1000)
    envelope = acp_encode(
        env_type="MSG",
        source="fcp",
        data={"tool_result": {"tool_use_id": call_id, "tool": tool,
                              "content": result, "_ts_ms": ts_ms}},
    )
    append_jsonl(layout.session_store, envelope)
    return ts_ms


def _session_byte_size(layout: Layout) -> int:
    if not layout.session_store.exists():
        return 0
    return layout.session_store.stat().st_size


def _load_baseline(layout: Layout) -> dict[str, Any]:
    try:
        return read_json(layout.baseline)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Verbose logging helpers
# ---------------------------------------------------------------------------

_DIM = "\x1b[2m"
_RESET = "\x1b[0m"


def _vprint(text: str) -> None:
    """Print verbose text in dim style."""
    print(f"{_DIM}{text}{_RESET}")


def _vlog(actor: str, msg: str) -> None:
    if not _is_verbose():
        return
    _vprint(f"[{actor}] {msg}")


def _vlog_json(label: str, data: Any) -> None:
    if not _is_verbose():
        return
    _vprint(f"[{label}]")
    _vprint(json.dumps(data, indent=2, ensure_ascii=False))


def _vlog_request(
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> None:
    dbg = _get_debugger()
    if not _is_verbose() and dbg is None:
        return

    if _is_verbose():
        # compact summary — counts only
        _vprint("[fcp→cpe] request")
        _vprint(f"  system       : {len(system)} chars")
        _vprint(f"  history msgs : {len(messages)}")
        _vprint(f"  tools        : {[t['name'] for t in tools]}")
        return

    # debugger mode
    _vprint("[debugger] fcp→cpe request")
    if dbg in ("boot", "all"):
        _vprint(f"  [system] {len(system)} chars:")
        for line in system.splitlines():
            _vprint(f"    {line}")
        _vprint(f"  [0] user (instruction block) {len(str(messages[0].get('content', '')))} chars:")
        for line in str(messages[0].get("content", "")).splitlines():
            _vprint(f"    {line}")
        _vprint(f"  [1] assistant: {messages[1].get('content', '')}")

    if dbg in ("chat", "all"):
        _vprint(f"  history ({len(messages) - 2} turns):")
        for i, msg in enumerate(messages):
            if i < 2:
                continue
            content = str(msg.get("content", ""))
            _vprint(f"    [{i}] {msg['role']}: {content}")

    _vprint(f"  tools: {[t['name'] for t in tools]}")


def _vlog_response(response: CPEResponse) -> None:
    if not _is_verbose() and _get_debugger() is None:
        return
    _vprint("[cpe→fcp] response")
    _vprint(f"  stop_reason  : {response.stop_reason}")
    _vprint(f"  tokens       : {response.input_tokens} in / {response.output_tokens} out")
    if response.text:
        preview = response.text[:200].replace("\n", " ")
        _vprint(f"  text         : {preview!r}")
    for call in response.tool_use_calls:
        _vprint(f"  tool_use     : {call.tool} (id={call.id})")


def _readline_with_history(prompt: str) -> str:
    """Read a line with up/down arrow history via readline if available."""
    try:
        import readline as _rl  # noqa: F401 — side-effect: enables arrow keys
    except ImportError:
        pass
    return input(prompt)


def _stage_evolution_proposal(layout: Layout, content: str) -> None:
    ts = int(time.time() * 1000)
    envelope = acp_encode(
        env_type="MSG",
        source="sil",
        data={"type": "PROPOSAL_PENDING", "content": content, "ts": ts},
    )
    dest = layout.operator_notifications_dir / f"{ts}_proposal_pending.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    os.replace(tmp, dest)


def _tool_declarations() -> list[dict[str, Any]]:
    return [
        {
            "name": "fcp_exec",
            "description": "Dispatch skill requests to the execution layer.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["skill_request", "skill_info"]},
                    "skill": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["type", "skill"],
            },
        },
        {
            "name": "fcp_mil",
            "description": "Memory operations: recall, write, or closure payload.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string",
                             "enum": ["memory_recall", "memory_write", "closure_payload", "result_recall"]},
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "slug": {"type": "string"},
                    "content": {"type": "string"},
                    "ts": {"type": "integer", "description": "Timestamp from a previous tool result summary, for result_recall."},
                },
                "required": ["type"],
            },
        },
        {
            "name": "fcp_sil",
            "description": "Integrity and session control signals.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type": {"type": "string",
                             "enum": ["evolution_proposal", "session_close"]},
                    "content": {"type": "string"},
                },
                "required": ["type"],
            },
        },
    ]
