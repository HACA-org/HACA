#!/usr/bin/env python3
"""core/cpe.py — Cognitive Processing Engine."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .acp import write as acp_write
from .config import Config
from .mil import MIL


class CPE:
    def __init__(self, root: Path, config: Config):
        self.root = root
        self.config = config

    def assemble_context(self, mil: MIL) -> str:
        parts = []

        # 1. Persona
        parts.append("--- [PERSONA] ---")
        persona_dir = self.root / "persona"
        if persona_dir.is_dir():
            for f in sorted(persona_dir.glob("*.md")):
                parts.append(f"\n### {f.name}\n{f.read_text()}")

        # 2. Boot Protocol
        parts.append("\n--- [BOOT PROTOCOL] ---")
        boot_md = self.root / "BOOT.md"
        if boot_md.exists():
            parts.append(boot_md.read_text())

        # 3. First Activation Protocol
        if os.environ.get("FCP_FAP_MODE") == "true":
            fap_file = os.environ.get("FCP_FAP_FILE", "")
            if fap_file and os.path.exists(fap_file):
                parts.append("\n--- [FIRST ACTIVATION PROTOCOL] ---")
                parts.append(open(fap_file).read())

        # 4. Environment
        parts.append("\n--- [ENV] ---")
        env_md = self.root / "state" / "env.md"
        if env_md.exists():
            parts.append(env_md.read_text())

        # 5. Active Context
        parts.append("\n--- [ACTIVE CONTEXT] ---")
        ctx_dir = self.root / "memory" / "active_context"
        if ctx_dir.is_dir():
            for link in sorted(ctx_dir.iterdir()):
                if link.name.startswith("."):
                    continue
                try:
                    parts.append(f"\n### {link.name}\n{link.read_text()}")
                except Exception:
                    pass

        # 6. Session History
        parts.append("\n--- [SESSION HISTORY] ---")
        parts.append(mil.read_context(self.config.context_budget_chars))

        return "\n".join(parts)

    def query(self, context: str) -> str:
        """Call LLM backend via llm_query.sh."""
        llm_query = self.root / "skills" / "llm_query.sh"
        if not llm_query.exists():
            return ""

        env = os.environ.copy()
        env["FCP_REF_ROOT"] = str(self.root)

        try:
            result = subprocess.run(
                [str(llm_query), context],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            print("[CPE] LLM query timeout", file=sys.stderr)
            return ""
        except Exception as e:
            print(f"[CPE] LLM query error: {e}", file=sys.stderr)
            return ""

    def parse_actions(self, output: str) -> list:
        """Extract fcp-actions block and return list of action dicts."""
        match = re.search(r'```fcp-actions\n(.*?)```', output, re.DOTALL)
        if not match:
            return []
        actions = []
        for line in match.group(1).strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                actions.append(json.loads(line))
            except Exception:
                pass
        return actions
