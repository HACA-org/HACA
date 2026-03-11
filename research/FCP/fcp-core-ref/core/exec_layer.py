#!/usr/bin/env python3
"""core/exec_layer.py — Execution Layer. No eval, no injection."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .acp import new_tx, write as acp_write
from .config import Config


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExecLayer:
    def __init__(self, root: Path, config: Config):
        self.root = root
        self.config = config
        self.skill_index = root / "skills" / "index.json"

    def authorize(self, skill_name: str):
        """Returns skill Path if authorized, None otherwise."""
        if not self.skill_index.exists():
            return None
        try:
            index = json.loads(self.skill_index.read_text())
        except Exception:
            return None
        for skill in index.get("skills", []):
            if skill.get("name") == skill_name:
                if skill.get("authorized", False):
                    return self.root / skill["path"]
        return None

    def execute(self, skill_name: str, params: dict) -> tuple:
        """Execute a skill. Returns (output, exit_code)."""
        skill_path = self.authorize(skill_name)
        if skill_path is None:
            print(f"[EXEC] REJECTED: skill '{skill_name}' not authorized", file=sys.stderr)
            self._log_acp("SKILL_ERROR", json.dumps({"skill": skill_name, "reason": "not_authorized"}))
            return "", 1

        manifest = skill_path / "manifest.json"
        if not manifest.exists():
            print(f"[EXEC] REJECTED: manifest missing for '{skill_name}'", file=sys.stderr)
            return "", 1

        tx = new_tx()
        self._log_acp("ACTION_PENDING", json.dumps({"skill": skill_name, "params": params, "tx": tx}), tx=tx)

        print(f"[EXEC] Executing: {skill_name}", file=sys.stderr)

        # Find executable — look for skill_name.sh first, then any .sh
        skill_script = skill_path / f"{skill_name}.sh"
        if not skill_script.exists():
            scripts = list(skill_path.glob("*.sh"))
            skill_script = scripts[0] if scripts else None

        if skill_script is None:
            print(f"[EXEC] ERROR: no executable found in {skill_path}", file=sys.stderr)
            self._log_acp("SKILL_ERROR", json.dumps({"skill": skill_name, "reason": "not_found", "tx": tx}))
            self._log_acp("ACTION_RESOLVED", json.dumps({"tx": tx, "status": 1}))
            return "", 1

        # Pass params as JSON in env var (no eval)
        env = os.environ.copy()
        env["SKILL_PARAMS_JSON"] = json.dumps(params)
        env["FCP_REF_ROOT"] = str(self.root)

        timeout = self.config.skill_timeout_seconds
        exit_code = 0
        output = ""
        try:
            result = subprocess.run(
                [str(skill_script), json.dumps(params)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            output = result.stdout
            if result.returncode != 0:
                output = (result.stdout + result.stderr).strip()
                exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
            print(f"[EXEC] TIMEOUT: {skill_name} ({timeout}s)", file=sys.stderr)
            self._log_acp("SKILL_TIMEOUT", json.dumps({"skill": skill_name, "timeout_s": timeout, "tx": tx}))
            self._log_acp("ACTION_RESOLVED", json.dumps({"tx": tx, "status": exit_code}))
            return "", exit_code
        except Exception as e:
            exit_code = 1
            output = str(e)

        if exit_code == 0:
            print(f"[EXEC] SUCCESS: {skill_name}", file=sys.stderr)
            self._log_acp("SKILL_RESULT", json.dumps({"skill": skill_name, "output": output, "tx": tx}))
        else:
            print(f"[EXEC] FAILED: {skill_name} (exit {exit_code})", file=sys.stderr)
            self._log_acp("SKILL_ERROR", json.dumps({"skill": skill_name, "error": output, "exit_code": exit_code, "tx": tx}))

        self._log_acp("ACTION_RESOLVED", json.dumps({"tx": tx, "status": exit_code}))
        return output, exit_code

    def _log_acp(self, typ: str, data: str, tx: str = None):
        try:
            acp_write("el", typ, data, self.root, tx=tx)
        except Exception as e:
            print(f"[EXEC] ACP write error: {e}", file=sys.stderr)
