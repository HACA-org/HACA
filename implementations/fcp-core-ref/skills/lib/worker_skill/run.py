#!/usr/bin/env python3
"""worker_skill — invoke a sub-agent CPE with isolated persona and task.

Params:
  task     (required) — the task description to give the worker
  persona  (optional) — system prompt / persona for the worker
  context  (optional) — additional context prepended to the task message
"""

from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", ".")).resolve()

    task = str(params.get("task", "")).strip()
    if not task:
        print(json.dumps({"error": "missing required param: task"}))
        sys.exit(1)

    persona = str(params.get("persona", "You are a focused sub-agent. Complete the given task concisely.")).strip()
    context = str(params.get("context", "")).strip()

    sys.path.insert(0, str(entity_root))
    from fcp_core.cpe.base import detect_adapter

    # read model from baseline.json if available
    model = ""
    baseline_path = entity_root / "state" / "baseline.json"
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            model = baseline.get("cpe", {}).get("model", "")
        except Exception:
            pass

    try:
        adapter = detect_adapter(model=model)
    except Exception as exc:
        print(json.dumps({"error": f"no CPE adapter available: {exc}"}))
        sys.exit(1)

    message = f"{context}\n\n{task}".strip() if context else task

    try:
        response = adapter.invoke(
            system=persona,
            messages=[{"role": "user", "content": message}],
            tools=[],
        )
    except Exception as exc:
        print(json.dumps({"error": f"CPE invocation failed: {exc}"}))
        sys.exit(1)

    print(json.dumps({"status": "ok", "result": response.text}))


main()
