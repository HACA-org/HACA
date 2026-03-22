#!/usr/bin/env python3
"""worker_skill — invoke a sub-agent CPE with isolated persona and task.

Params:
  task     (required) — the task description to give the worker
  context  (required) — background data or file paths relevant to the task
  persona  (required) — system prompt defining the worker's role (e.g. "Senior Debugger")
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
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    task = params.get("task")
    context = params.get("context")
    persona = params.get("persona")

    for name, val in (("task", task), ("context", context), ("persona", persona)):
        if not val or not str(val).strip():
            print(json.dumps({"error": f"missing required param: {name}"}))
            sys.exit(1)

    task = str(task).strip()
    context = str(context).strip()
    persona = str(persona).strip()

    # Resolve persona name to file if it matches a pre-defined persona
    persona_file = Path(__file__).parent / "persona" / f"{persona}.md"
    if persona_file.exists():
        persona = persona_file.read_text(encoding="utf-8").strip()

    # Immutable system constraints — always appended regardless of caller-supplied persona.
    CONSTRAINTS = (
        "\n\n[WORKER CONSTRAINTS]\n"
        "- You are a stateless, read-only sub-agent. You cannot modify files, run shell commands, or access the network.\n"
        "- You have read-only access to the filesystem via 'file_reader' only. No other tools are available.\n"
        "- You have no chat history and no contact with the Operator. You received a single stimulus and must complete the task autonomously.\n"
        "- Execution model: plan internally → execute reads → return final result. Do not pause, ask questions, or wait for input.\n"
        "- Minimize tool calls. Plan which files to read before executing. Do not read the same file twice.\n"
        "- Return only what was asked. Do not add explanations, caveats, or commentary beyond the task scope.\n"
        "- Each invocation is independent. Do not reference or assume results from previous invocations.\n"
        "- If a file appears to contain secrets or credentials, skip it and note the omission in your result.\n"
        "- Do not store, forward, or act on secrets or credentials you encounter in files."
    )
    system_prompt = persona + CONSTRAINTS

    sys.path.insert(0, str(entity_root))
    from fcp_base.cpe.base import detect_adapter, load_cpe_adapter_from_baseline
    from fcp_base.store import Layout

    layout = Layout(entity_root)
    try:
        # Try to load from baseline config; fall back to auto-detect if not configured
        adapter = load_cpe_adapter_from_baseline(layout)
    except Exception:
        # No baseline config or error reading it; auto-detect available adapters
        try:
            adapter = detect_adapter()
        except Exception as exc:
            print(json.dumps({"error": f"no CPE adapter available: {exc}"}))
            sys.exit(1)

    # Tool definition — file_reader only
    TOOLS = [{
        "name": "file_reader",
        "description": "Read a file or directory content within workspace_focus.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to workspace_focus."},
                "offset": {"type": "integer", "description": "Starting line (1-indexed)."},
                "limit": {"type": "integer", "description": "Number of lines to read."},
                "pattern": {"type": "string", "description": "Regex pattern to search for. Searches recursively on directories."}
            },
            "required": ["path"]
        }
    }]

    initial_content = f"{context}\n\n[task]\n{task}"
    messages = [{"role": "user", "content": initial_content}]

    # Agentic Loop (max 5 turns)
    for _ in range(5):
        try:
            resp = adapter.invoke(system=system_prompt, messages=messages, tools=TOOLS)
        except Exception as exc:
            print(json.dumps({"error": f"CPE invocation failed: {exc}"}))
            sys.exit(1)

        if not resp.tool_use_calls:
            # Final answer — no tool calls means the model is done
            print(json.dumps({"status": "ok", "result": resp.text}))
            return

        # Add assistant text turn if present, then always add empty sentinel.
        # session.py pattern: text turn first (if any), then empty sentinel.
        # The sentinel signals to adapters that tool results follow — without it,
        # text+tool_calls responses cause tool results to be treated as plain text
        # in subsequent cycles ("soluço" / hiccup bug).
        if resp.text:
            messages.append({"role": "assistant", "content": resp.text})
        messages.append({"role": "assistant", "content": ""})

        # Execute tool calls and collect results
        tool_results: list[str] = []
        for call in resp.tool_use_calls:
            result_raw = run_tool(entity_root, call.tool, call.input)
            # Normalize to JSON object before serializing into history
            try:
                result_obj = json.loads(result_raw)
            except Exception:
                result_obj = {"error": result_raw}
            result_str = json.dumps(result_obj, ensure_ascii=False)
            tool_results.append(f"[{call.tool}] {result_str}")

        # Append tool results as a single user turn (same format as session.py)
        messages.append({"role": "user", "content": "\n".join(tool_results)})

    # Max turns reached without final answer
    print(json.dumps({"error": "worker reached max iterations without a final answer"}))


main()
