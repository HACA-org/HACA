#!/usr/bin/env python3
"""worker_skill — invoke a sub-agent CPE with isolated persona and task.

Params:
  task     (required) — the task description to give the worker
  persona  (optional) — system prompt / persona for the worker
  context  (optional) — additional context prepended to the task message
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_tool(entity_root: Path, tool_name: str, params: dict[str, Any]) -> str:
    """Execute a skill script and return its stdout."""
    # Only file_reader is allowed for the Worker
    if tool_name != "file_reader":
        return json.dumps({"error": f"Tool not allowed for worker: {tool_name}"})
        
    exe = entity_root / "skills" / "lib" / tool_name / "run.py"
    if not exe.exists():
        return json.dumps({"error": f"Tool script not found: {tool_name}"})
        
    # inherit the entity_root for the sub-tool
    input_data = json.dumps({"params": params, "entity_root": str(entity_root)})
    try:
        res = subprocess.run(
            ["python3", str(exe)],
            input=input_data,
            text=True,
            capture_output=True,
            timeout=60
        )
        return res.stdout.strip()
    except Exception as exc:
        return json.dumps({"error": f"Tool execution failed: {exc}"})


def main() -> None:
    import subprocess
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    task = str(params.get("task", "")).strip()
    context = str(params.get("context", "")).strip()
    persona = str(params.get("persona", "You are a focused sub-agent.")).strip()

    if not task:
        print(json.dumps({"error": "missing required param: task"}))
        sys.exit(1)

    # Note: No restrictive constraint here anymore, just a focused persona.
    persona += (
        "\n\n[SYSTEM CONTEXT]\n"
        "You have read-only access to the filesystem via 'file_reader'. "
        "Use it to explore and analyze files within the workspace_focus before providing your answer."
    )

    sys.path.insert(0, str(entity_root))
    from fcp_base.cpe.base import detect_adapter, make_adapter

    # read backend/model from baseline.json
    backend, model, api_key = "", "", ""
    baseline_path = entity_root / "state" / "baseline.json"
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            cpe_cfg = baseline.get("cpe", {})
            backend, model, api_key = cpe_cfg.get("backend", ""), cpe_cfg.get("model", ""), cpe_cfg.get("api_key", "")
        except Exception: pass

    try:
        adapter = make_adapter(backend, api_key, model) if backend else detect_adapter(model=model)
    except Exception as exc:
        print(json.dumps({"error": f"no CPE adapter available: {exc}"}))
        sys.exit(1)

    # Tool definition
    TOOLS = [{
        "name": "file_reader",
        "description": "Read a file or directory content within workspace_focus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to workspace_focus."},
                "offset": {"type": "integer", "description": "Starting line (1-indexed)."},
                "limit": {"type": "integer", "description": "Number of lines to read."}
            },
            "required": ["path"]
        }
    }]

    messages = [{"role": "user", "content": f"Context: {context}\n\nTask: {task}"}]
    
    # Agentic Loop (max 5 turns)
    for _ in range(5):
        try:
            resp = adapter.invoke(system=persona, messages=messages, tools=TOOLS)
        except Exception as exc:
            print(json.dumps({"error": f"CPE invocation failed: {exc}"}))
            sys.exit(1)

        if not resp.tool_use_calls:
            # Final answer
            print(json.dumps({"status": "ok", "result": resp.text}))
            return

        # Prepare tool results
        history_text = resp.text
        # Append assistant turn (empty text if just tool use)
        messages.append({"role": "assistant", "content": history_text})
        
        results_content = []
        for call in resp.tool_use_calls:
            tool_name = call.tool
            tool_input = call.input
            result = run_tool(entity_root, tool_name, tool_input)
            # Standard FCP tool result format for the next turn
            results_content.append(f"[tool result: {tool_name}]\n{result}")

        # Append tool results as a user turn
        messages.append({"role": "user", "content": "\n".join(results_content)})

    # Max turns reached
    print(json.dumps({"status": "error", "message": "worker reached max iterations without a final answer"}))


main()
