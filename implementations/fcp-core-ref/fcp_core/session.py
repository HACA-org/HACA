"""
Session loop — FCP-Core §6.

Drives the cognitive cycle:
  drain io/inbox/ → consolidate → assemble context → invoke CPE
  → process tool_use → return tool_results → repeat

Session ends on session_close signal (CPE, SIL, or Operator).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from .acp import drain_inbox, make as acp_encode
from .cpe.base import CPEAdapter, FCPContext
from .mil import memory_recall, write_episodic
from .store import Layout, append_jsonl, atomic_write, read_json, read_jsonl


# ---------------------------------------------------------------------------
# Main session loop
# ---------------------------------------------------------------------------

def run_session(
    layout: Layout,
    adapter: CPEAdapter,
    index: dict[str, Any],
    *,
    inject: list[dict[str, Any]] | None = None,
) -> str:
    """Run the cognitive session loop until session close.

    inject: optional list of ACP envelopes to prepend as first stimuli.
    Returns the close reason string.
    """
    if inject:
        for env in inject:
            append_jsonl(layout.session_store, env)

    close_reason = "session_close"

    while True:
        # drain io/inbox/ → consolidate to session.jsonl
        _drain_and_consolidate(layout)

        # check context budget
        baseline = _load_baseline(layout)
        budget = int(baseline.get("context_budget", {}).get(
            "session_critical_threshold", 50000))
        if _session_byte_size(layout) >= budget:
            close_reason = "context_window_critical"
            break

        # assemble context
        ctx = assemble_context(layout, index)

        # invoke CPE
        response = adapter.invoke(ctx)

        # display narrative
        if response.text:
            _append_msg(layout, "cpe", response.text)
            print(response.text)

        # process tool_use calls — fcp_mil before fcp_exec before fcp_sil (per spec)
        tool_calls = sorted(
            response.tool_use_calls,
            key=lambda c: 0 if c.tool == "fcp_mil" else (1 if c.tool == "fcp_exec" else 2),
        )

        session_closed = False
        for call in tool_calls:
            result, closed = dispatch_tool_use(layout, call, index)
            _return_tool_result(layout, call.id, call.tool, result)
            if closed:
                close_reason = "session_close"
                session_closed = True

        if session_closed:
            break

        # no tool calls — wait for next operator input
        if not response.tool_use_calls:
            try:
                user_input = input("> ")
            except EOFError:
                close_reason = "operator_eof"
                break
            if user_input.strip():
                _append_msg(layout, "operator", user_input)

    return close_reason


# ---------------------------------------------------------------------------
# Context assembly  §5.1
# ---------------------------------------------------------------------------

def assemble_context(layout: Layout, index: dict[str, Any]) -> FCPContext:
    """Assemble the CPE input context following the Boot Manifest order."""
    # [PERSONA]
    persona: list[str] = []
    if layout.persona_dir.exists():
        for p in sorted(layout.persona_dir.iterdir()):
            if p.is_file():
                persona.append(p.read_text(encoding="utf-8"))

    # [BOOT PROTOCOL]
    boot_protocol = ""
    if layout.boot_md.exists():
        boot_protocol = layout.boot_md.read_text(encoding="utf-8")

    # [SKILLS INDEX] summary + [SKILL:<name>] blocks
    skills_index_str = ""
    skill_blocks: list[str] = []
    if layout.skills_index.exists():
        idx = read_json(layout.skills_index)
        visible = [s for s in idx.get("skills", []) if s.get("class") != "operator"]
        skills_index_str = json.dumps(
            {"skills": [{"name": s["name"], "desc": s.get("desc", "")} for s in visible]},
            indent=2,
        )
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

    # [MEMORY] — working-memory targets in priority order
    memory: list[str] = []
    if layout.working_memory.exists():
        wm = read_json(layout.working_memory)
        for entry in sorted(wm.get("entries", []), key=lambda e: int(e.get("priority", 99))):
            p = layout.root / entry.get("path", "")
            if p.exists():
                memory.append(p.read_text(encoding="utf-8"))

    # [SESSION] — newest-first
    session_records = list(reversed(read_jsonl(layout.session_store)))

    # [PRESESSION]
    presession: list[dict[str, Any]] = []
    if layout.presession_dir.exists():
        for f in sorted(layout.presession_dir.iterdir()):
            if f.suffix == ".json":
                try:
                    presession.append(json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    pass

    return FCPContext(
        persona=persona,
        boot_protocol=boot_protocol,
        skills_index=skills_index_str,
        skill_blocks=skill_blocks,
        memory=memory,
        session=session_records,
        presession=presession,
        tools=_tool_declarations(),
    )


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
    from .exec_ import dispatch, SkillRejected
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "skill_request":
            skill_name = str(action.get("skill", ""))
            params = action.get("params", {})
            try:
                output = dispatch(layout, skill_name, params, index)
                results.append({"type": "skill_request", "skill": skill_name,
                                 "status": "dispatched", "output": output})
            except SkillRejected as exc:
                results.append({"type": "skill_request", "skill": skill_name,
                                 "error": str(exc)})
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

def _drain_and_consolidate(layout: Layout) -> None:
    envelopes = drain_inbox(layout.inbox_dir)
    for env in envelopes:
        append_jsonl(layout.session_store, env)


def _append_msg(layout: Layout, source: str, text: str) -> None:
    envelope = acp_encode(env_type="MSG", source=source, data=text)
    append_jsonl(layout.session_store, envelope)


def _return_tool_result(
    layout: Layout, call_id: str, tool: str, result: dict[str, Any]
) -> None:
    envelope = acp_encode(
        env_type="MSG",
        source="fcp",
        data={"tool_result": {"tool_use_id": call_id, "tool": tool, "content": result}},
    )
    append_jsonl(layout.session_store, envelope)


def _session_byte_size(layout: Layout) -> int:
    if not layout.session_store.exists():
        return 0
    return layout.session_store.stat().st_size


def _load_baseline(layout: Layout) -> dict[str, Any]:
    try:
        return read_json(layout.baseline)
    except Exception:
        return {}


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
                    "type": {"type": "string", "enum": ["skill_request"]},
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
                             "enum": ["memory_recall", "memory_write", "closure_payload"]},
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "slug": {"type": "string"},
                    "content": {"type": "string"},
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
