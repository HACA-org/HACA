"""Execution Layer (EXEC) — FCP-Core §9 MVP subset.

The EXEC is the sole component authorized to execute skills against the host.

Two-gate authorization model (§9.2):
  Gate 1 — Skill Index check (skills/index.json, loaded at boot by SIL)
  Gate 2 — Manifest validation at dispatch time (permissions, params)

MVP scope (Fase 1):
  - Skill Index loading and lookup (Gate 1)
  - Manifest validation (Gate 2, basic param check)
  - Synchronous subprocess skill execution with timeout
  - SKILL_RESULT / SKILL_ERROR written to io/inbox/
  - Slash command resolution

Deferred to Fase 2:
  - Background / async skill execution
  - Worker skills (CPE-invoked sub-agents)
  - Action Ledger integration (irreversible side effects)
  - Retry counter (fault.n_retry)
"""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .acp import (
    ACPEnvelope,
    GseqCounter,
    ACTOR_EXEC,
    TYPE_SKILL_RESULT,
    TYPE_SKILL_ERROR,
    TYPE_SKILL_TIMEOUT,
    TYPE_STRUCTURAL_ANOMALY,
    build_envelope,
    chunk_payload,
)
from .fs import (
    read_json,
    spool_msg,
    utcnow_iso,
)
from .hooks import run_hook
from .sil import append_integrity_log


# ---------------------------------------------------------------------------
# Skill Index (§9.1)
# ---------------------------------------------------------------------------

class SkillIndex:
    """In-memory representation of skills/index.json.

    Loaded once per session at Boot Phase 4.  The on-disk file was already
    verified by the SIL (hash check) at Phase 3 — EXEC trusts this in-memory
    representation for the session duration.
    """

    def __init__(self, index_data: dict[str, Any]) -> None:
        self._data = index_data
        # Map: skill_name → skill entry
        self._skills: dict[str, dict[str, Any]] = {
            s["name"]: s for s in index_data.get("skills", [])
        }
        # Map: /alias → skill_name
        self._aliases: dict[str, str] = {}
        for skill in self._skills.values():
            for alias in skill.get("aliases", []):
                self._aliases[alias] = skill["name"]

    def get(self, skill_name: str) -> dict[str, Any] | None:
        """Return the skill entry for *skill_name*, or None."""
        return self._skills.get(skill_name)

    def resolve_alias(self, alias: str) -> str | None:
        """Return the skill name for a slash-command *alias*, or None."""
        return self._aliases.get(alias)

    def all_names(self) -> list[str]:
        return list(self._skills.keys())

    def all_aliases(self) -> list[str]:
        return list(self._aliases.keys())


def load_skill_index(entity_root: str | Path) -> SkillIndex:
    """Load ``skills/index.json`` and return a SkillIndex.

    Raises:
        FileNotFoundError: if the index file is absent.
        ValueError: if the file is malformed.
    """
    path = Path(entity_root) / "skills" / "index.json"
    if not path.exists():
        raise FileNotFoundError(f"skills/index.json not found at {entity_root}")
    data = read_json(path)
    return SkillIndex(data)


def build_skill_index(entity_root: str | Path) -> dict[str, Any]:
    """Scan ``skills/`` and produce the skills/index.json content.

    Only skills with a valid manifest.json are included (§9.1 / §4 step 1).
    execute.* is optional; skills without one are included but not executable.
    """
    entity_root = Path(entity_root)
    skills_dir  = entity_root / "skills"
    skills: list[dict[str, Any]] = []

    if not skills_dir.exists():
        return {"version": "1.0", "skills": []}

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name == "lib":
            continue  # system skills — not visible to CPE
        manifest_path = skill_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = read_json(manifest_path)
        except Exception:
            continue
        if "name" not in manifest:
            continue
        # Locate executable (optional)
        exe: Path | None = None
        for exe_name in ("execute.sh", "execute.py"):
            candidate = skill_dir / exe_name
            if candidate.exists():
                exe = candidate
                break
        manifest["_executable"] = str(exe.relative_to(entity_root)) if exe else ""
        # Narrative presence flag
        narrative = skill_dir / f"{skill_dir.name}.md"
        manifest["_has_narrative"] = narrative.exists()
        skills.append(manifest)

    return {"version": "1.0", "skills": skills}


# ---------------------------------------------------------------------------
# Manifest validation — Gate 2 (§9.2)
# ---------------------------------------------------------------------------

def _validate_manifest(
    manifest: dict[str, Any],
    params:   dict[str, Any],
) -> list[str]:
    """Return a list of validation errors (empty = valid)."""
    errors: list[str] = []
    declared_params: dict[str, str] = manifest.get("params", {})
    for param_name, _param_type in declared_params.items():
        if param_name not in params:
            errors.append(f"missing required parameter: {param_name!r}")
    return errors


# ---------------------------------------------------------------------------
# Dispatch (§9.2)
# ---------------------------------------------------------------------------

class ExecDispatcher:
    """Stateful dispatcher for the current session.

    Holds the skill index and gseq counter.  Used by the session loop and
    the operator interface (slash commands).
    """

    def __init__(
        self,
        entity_root:  str | Path,
        skill_index:  SkillIndex,
        gseq_counter: GseqCounter,
        session_id:   str = "",
    ) -> None:
        self.entity_root  = Path(entity_root)
        self.skill_index  = skill_index
        self.gseq_counter = gseq_counter
        self.session_id   = session_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dispatch_skill(
        self,
        skill_name: str,
        params:     dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute skill *skill_name* with *params*.

        Steps:
          1. Gate 1 — Skill Index lookup
          2. Gate 2 — Manifest param validation
          3. Subprocess execution (with timeout)
          4. Write SKILL_RESULT or SKILL_ERROR to io/inbox/

        Returns:
            List of ACP envelope dicts written to io/inbox/.
        """
        # --- Gate 1 ---
        entry = self.skill_index.get(skill_name)
        if entry is None:
            msg = f"Skill {skill_name!r} not in index — possible structural anomaly."
            self._log_structural_anomaly(skill_name, msg)
            return self._write_skill_error(skill_name, msg)

        # --- Gate 2 ---
        errors = _validate_manifest(entry, params)
        if errors:
            msg = f"Manifest validation failed: {'; '.join(errors)}"
            self._log_structural_anomaly(skill_name, msg)
            return self._write_skill_error(skill_name, msg)

        # --- Hooks: pre_skill ---
        run_hook(self.entity_root, "pre_skill", self.session_id, {
            "FCP_SKILL_NAME":   skill_name,
            "FCP_SKILL_PARAMS": json.dumps(params),
        })

        # --- Execute ---
        results = self._execute(skill_name, entry, params)

        # --- Hooks: post_skill ---
        _STATUS = {
            TYPE_SKILL_RESULT:  "success",
            TYPE_SKILL_ERROR:   "error",
            TYPE_SKILL_TIMEOUT: "timeout",
        }
        status = _STATUS.get(results[0]["type"] if results else "", "error")
        run_hook(self.entity_root, "post_skill", self.session_id, {
            "FCP_SKILL_NAME":   skill_name,
            "FCP_SKILL_STATUS": status,
        })

        return results

    def dispatch_slash(self, slash_input: str) -> list[dict[str, Any]]:
        """Resolve and dispatch a slash command (§12.3).

        Args:
            slash_input: Raw operator input starting with '/'.

        Returns:
            Result envelopes, or an error if the command is unrecognised.
        """
        parts = slash_input.strip().split(None, 1)
        alias = parts[0]
        raw_params = parts[1] if len(parts) > 1 else ""

        skill_name = self.skill_index.resolve_alias(alias)
        if skill_name is None:
            return self._write_skill_error(
                alias,
                f"Unknown slash command {alias!r}.  "
                f"Available: {', '.join(self.skill_index.all_aliases())}",
            )

        # Simple param parsing for slash commands: key=value pairs
        params: dict[str, Any] = {}
        if raw_params:
            for token in raw_params.split():
                if "=" in token:
                    k, _, v = token.partition("=")
                    params[k] = v

        return self.dispatch_skill(skill_name, params)

    def dispatch_skill_info(self, skill_name: str) -> list[dict[str, Any]]:
        """Read skills/<skill_name>/<skill_name>.md and spool as SKILL_RESULT.

        Returns error envelope if skill not found or narrative absent.
        """
        entry = self.skill_index.get(skill_name)
        if entry is None:
            return self._write_skill_error(
                skill_name,
                f"Skill {skill_name!r} not found in index.",
            )
        if not entry.get("_has_narrative"):
            return self._write_skill_error(
                skill_name,
                f"No narrative ({skill_name}.md) for skill {skill_name!r}.",
            )
        narrative_path = self.entity_root / "skills" / skill_name / f"{skill_name}.md"
        try:
            content = narrative_path.read_text(encoding="utf-8")
        except OSError as exc:
            return self._write_skill_error(skill_name, f"Could not read narrative: {exc}")
        return self._write_skill_result(skill_name, content)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute(
        self,
        skill_name: str,
        entry:      dict[str, Any],
        params:     dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Run the skill's executable as a subprocess and return result envelopes."""
        exe_rel  = entry.get("_executable", "")
        if not exe_rel:
            return self._write_skill_error(
                skill_name,
                f"Skill {skill_name!r} has no executable (execute.sh / execute.py).",
            )
        exe_path = self.entity_root / exe_rel
        timeout  = entry.get("timeout_seconds", 60)

        # Build environment: pass params as FCP_PARAM_<NAME>=<VALUE>
        env = os.environ.copy()
        env["FCP_ENTITY_ROOT"] = str(self.entity_root)
        env["FCP_SKILL_NAME"]  = skill_name
        for k, v in params.items():
            env[f"FCP_PARAM_{k.upper()}"] = str(v)

        try:
            result = subprocess.run(
                [str(exe_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(self.entity_root),
            )
            if result.returncode == 0:
                output = result.stdout.strip() or f"Skill {skill_name} completed."
                return self._write_skill_result(skill_name, output)
            else:
                error = result.stderr.strip() or f"Exit code {result.returncode}"
                return self._write_skill_error(skill_name, error)

        except subprocess.TimeoutExpired:
            return self._write_skill_error(
                skill_name,
                f"Skill {skill_name!r} timed out after {timeout}s.",
                type_=TYPE_SKILL_TIMEOUT,
            )
        except Exception as exc:
            return self._write_skill_error(skill_name, str(exc))

    def _log_structural_anomaly(self, skill_name: str, reason: str) -> None:
        """Log a structural anomaly to integrity.log (§9.1).

        Gate 1 (skill absent) and Gate 2 (manifest fail) failures are logged
        here so the SIL has a persistent record for post-session analysis.
        """
        env = build_envelope(
            actor=ACTOR_EXEC,
            type_=TYPE_STRUCTURAL_ANOMALY,
            data=json.dumps({"skill": skill_name, "reason": reason, "ts": utcnow_iso()}),
            gseq=self.gseq_counter.next(),
        )
        append_integrity_log(self.entity_root, env)

    def _write_skill_result(
        self,
        skill_name: str,
        output:     str,
    ) -> list[dict[str, Any]]:
        payload = json.dumps({
            "skill":  skill_name,
            "status": "ok",
            "output": output,
            "ts":     utcnow_iso(),
        })
        envelopes = chunk_payload(
            actor=ACTOR_EXEC,
            type_=TYPE_SKILL_RESULT,
            payload_str=payload,
            gseq_start=self.gseq_counter.next(),
        )
        result = []
        for env in envelopes:
            spool_msg(self.entity_root, env.to_dict())
            result.append(env.to_dict())
        return result

    def _write_skill_error(
        self,
        skill_name: str,
        error:      str,
        type_:      str = TYPE_SKILL_ERROR,
    ) -> list[dict[str, Any]]:
        payload = json.dumps({
            "skill":  skill_name,
            "status": "error",
            "error":  error,
            "ts":     utcnow_iso(),
        })
        envelopes = chunk_payload(
            actor=ACTOR_EXEC,
            type_=type_,
            payload_str=payload,
            gseq_start=self.gseq_counter.next(),
        )
        result = []
        for env in envelopes:
            spool_msg(self.entity_root, env.to_dict())
            result.append(env.to_dict())
        return result
