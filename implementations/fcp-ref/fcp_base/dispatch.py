"""
Tool call routing — FCP §6.2.

Receives a single tool_use call from the cognitive loop and routes it to the
appropriate component: MIL, CMI, SIL, EXEC, or skill_info.

Entry point: dispatch_tool_use(layout, call, index) -> (result_dict, session_closed)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .mil import memory_recall, result_recall, write_episodic
from .operator import set_endure_approved as _set_endure_approved
from .sil import sha256_str as _sha256_str, stage_evolution_proposal as _stage_evolution_proposal, write_evolution_auth as _write_evolution_auth
from .stimuli import inject_evolution_result as _write_evolution_stimuli
from .store import Layout, atomic_write, load_baseline

_log = logging.getLogger(__name__)


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
        except json.JSONDecodeError:
            pass
        except Exception as e:
            _log.debug("tool input action parse error (%s) — using raw action", e)

    # --- MIL tools ---
    if tool in ("memory_recall", "memory_write", "result_recall", "closure_payload"):
        action = dict(inp)
        action["type"] = tool
        return _dispatch_mil(layout, action)

    # --- CMI tools ---
    if tool in ("cmi_send", "cmi_req"):
        return _dispatch_cmi(layout, tool, inp)

    # --- SIL tools ---
    if tool in ("session_close", "evolution_proposal"):
        action = dict(inp)
        action["type"] = tool
        return _dispatch_sil(layout, action)

    # --- skill_info ---
    if tool == "skill_info":
        skill_name = str(inp.get("skill", ""))
        return _skill_info(layout, skill_name, index), False

    # --- skills by name ---
    skill_names = {s.get("name") for s in index.get("skills", [])}
    if tool in skill_names:
        exec_inp = {"type": "skill_request", "skill": tool, "params": inp}
        return _dispatch_exec(layout, exec_inp, index)

    # --- legacy fcp_* names (backwards compat during transition) ---
    if tool == "fcp_mil":
        return _dispatch_mil(layout, inp)
    if tool == "fcp_exec":
        return _dispatch_exec(layout, inp, index)
    if tool == "fcp_sil":
        return _dispatch_sil(layout, inp)

    return {"error": f"unknown tool: {tool}"}, False


def _dispatch_cmi(
    layout: Layout, tool: str, params: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Dispatch CMI tools (cmi_send, cmi_req) to the CMI component."""
    from .cmi.dispatch import dispatch_send, dispatch_req
    if tool == "cmi_send":
        result = dispatch_send(layout, params)
    else:
        result = dispatch_req(layout, params)
    return result, False


def _dispatch_mil(
    layout: Layout, inp: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Dispatch Memory Interface Layer (MIL) actions."""
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "memory_recall":
            raw_path = action.get("path") or ""
            result = memory_recall(layout, str(action.get("query", "")),
                                   str(raw_path) if raw_path else "")
            results.append({"type": "memory_recall", "result": result})
        elif atype == "result_recall":
            ts = int(action.get("ts", 0))
            result = result_recall(layout, ts)
            results.append({"type": "result_recall", "result": result})
        elif atype == "memory_write":
            slug = str(action.get("slug", "")).strip()
            content = str(action.get("content", ""))
            overwrite = bool(action.get("overwrite", False))
            if not slug:
                results.append({"type": "memory_write", "status": "error", "message": "slug is required and must not be empty."})
            else:
                outcome = write_episodic(layout, slug, content, overwrite=overwrite)
                if isinstance(outcome, dict):
                    results.append({
                        "type": "memory_write",
                        "status": "conflict",
                        "slug": slug,
                        "existing_content": outcome["existing_content"],
                        "message": "A memory with this slug already exists. Call memory_write again with overwrite=true to replace it, or use a different slug.",
                    })
                else:
                    results.append({"type": "memory_write", "status": "ok"})
        elif atype == "closure_payload":
            payload = {k: v for k, v in action.items() if k != "type"}
            atomic_write(layout.pending_closure, payload)
            results.append({"type": "closure_payload", "status": "acknowledged"})
        else:
            results.append({"type": atype, "error": "unknown mil action"})
    return {"results": results}, False


def _dispatch_exec(
    layout: Layout,
    inp: dict[str, Any],
    index: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Dispatch Execution Interface (skill requests)."""
    from .exec_ import dispatch, ExecError, SkillRejected
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    for action in actions:
        atype = action.get("type", "")
        if atype == "skill_request":
            skill_name = str(action.get("skill", ""))
            params = action.get("params", {})
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    _log.debug("skill params not valid JSON, using empty dict")
                    params = {}
                except Exception as e:
                    _log.debug("skill params parse error (%s), using empty dict", e)
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
    """Dispatch System Interface Layer (SIL) actions."""
    actions: list[Any] = inp if isinstance(inp, list) else [inp]
    results: list[dict[str, Any]] = []
    session_closed = False
    for action in actions:
        atype = action.get("type", "")
        if atype == "evolution_proposal":
            payload = {k: v for k, v in action.items() if k != "type"}
            content = json.dumps(payload)
            proposal_file = _stage_evolution_proposal(layout, content)
            try:
                baseline = load_baseline(layout)
                profile = baseline.get("profile", "haca-core")
                autonomous = (
                    profile == "haca-evolve"
                    and baseline.get("evolve", {}).get("scope", {}).get("autonomous_evolution", False)
                )
            except FileNotFoundError:
                _log.debug("baseline not found — autonomous evolution disabled")
                autonomous = False
            except Exception as e:
                _log.debug("baseline load error (%s) — autonomous evolution disabled", e)
                autonomous = False
            if autonomous:
                auth_digest = _sha256_str(content)
                _write_evolution_auth(layout, content, auth_digest)
                _write_evolution_stimuli(layout, payload.get("description", content), approved=True)
                proposal_file.unlink(missing_ok=True)
                _set_endure_approved(True)
                results.append({"type": "evolution_proposal", "status": "auto_approved"})
                session_closed = True
            else:
                results.append({"type": "evolution_proposal", "status": "queued"})
        elif atype == "session_close":
            session_closed = True
            results.append({"type": "session_close", "status": "acknowledged"})
        else:
            results.append({"type": atype, "error": "unknown sil action"})
    return {"results": results}, session_closed


def _skill_info(
    layout: Layout, skill_name: str, index: dict[str, Any]
) -> dict[str, Any]:
    """Return the manifest JSON of a skill, or an error."""
    for entry in index.get("skills", []):
        if entry.get("name") == skill_name:
            rel = entry.get("manifest", "")
            if rel:
                mpath = layout.root / rel
                if mpath.exists():
                    return {"type": "skill_info", "skill": skill_name,
                            "content": mpath.read_text(encoding="utf-8")}
            return {"type": "skill_info", "skill": skill_name, "error": "no manifest path"}
    return {"type": "skill_info", "skill": skill_name, "error": "skill not in index"}
