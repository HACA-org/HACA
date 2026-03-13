#!/usr/bin/env python3
"""worker_skill — invoke a sub-agent CPE with isolated persona, context, and task."""

from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", "."))

    persona = str(params.get("persona", "")).strip()
    context = str(params.get("context", "")).strip()
    task = str(params.get("task", "")).strip()

    if not task:
        print(json.dumps({"error": "missing required param: task"}))
        sys.exit(1)

    # Detect adapter and invoke with minimal FCPContext
    sys.path.insert(0, str(entity_root.parent))
    from fcp_core.cpe.base import detect_adapter, FCPContext

    adapter = detect_adapter()
    ctx = FCPContext(
        persona=[persona] if persona else [],
        boot_protocol="",
        skills_index="",
        skill_blocks=[],
        memory=[context] if context else [],
        session=[],
        presession=[],
        tools=[],
    )
    response = adapter.invoke(ctx)
    print(json.dumps({"status": "ok", "result": response.text}))


main()
