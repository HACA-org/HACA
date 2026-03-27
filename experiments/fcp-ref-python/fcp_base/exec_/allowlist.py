"""
Execution allowlist management — FCP §9 / §10.

Covers two distinct layers:

  1. ExecutionPermissions / AllowlistEntry / PermissionScope — structured
     permission model stored in baseline.exec_allowlist (used by operator.py
     for the /allowlist command).

  2. _maybe_prompt_shell_allowlist / _maybe_prompt_web_allowlist — runtime
     interception: when a skill returns an "not in allowlist" error these
     functions offer the operator an approval gate (allow_once / allow_always
     / deny) and persist the decision.

  3. _shell_allowlist_add / _web_allowlist_add — low-level writers that
     persist a newly approved entry to the relevant skill manifest.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from ..approval import ApprovalDecision, request_approval
from .. import ui

if TYPE_CHECKING:
    from ..store import Layout


# ---------------------------------------------------------------------------
# Permission model (baseline.exec_allowlist)
# ---------------------------------------------------------------------------

class PermissionScope(str, Enum):
    """Permission scope categories."""
    SHELL_RUN = "shell_run"
    FILE_OPS = "file_ops"
    SYSTEM_OPS = "system_ops"


@dataclass
class AllowlistEntry:
    """Single allowlist entry for a command or action."""
    command: str
    scope: str  # PermissionScope value
    reason: str = ""
    added_at: str = ""

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "scope": self.scope,
            "reason": self.reason,
            "added_at": self.added_at or "",
        }


class ExecutionPermissions:
    """Manage execution permissions and allowlists."""

    def __init__(self, permissions_dict: dict | None = None):
        self._permissions: dict[str, list[dict]] = permissions_dict or {}

    @staticmethod
    def load_from_baseline(layout: "Layout") -> "ExecutionPermissions":
        from ..store import read_json
        baseline: dict = {}
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
        return ExecutionPermissions(baseline.get("exec_allowlist", {}))

    def has_permission(self, command: str, scope: str) -> bool:
        return any(e.get("command") == command for e in self._permissions.get(scope, []))

    def add_entry(self, command: str, scope: str, reason: str = "") -> None:
        if not isinstance(scope, str):
            scope = scope.value
        scope_list = self._permissions.setdefault(scope, [])
        if any(e.get("command") == command for e in scope_list):
            return
        entry = AllowlistEntry(
            command=command,
            scope=scope,
            reason=reason,
            added_at=str(int(time.time())),
        )
        scope_list.append(entry.to_dict())

    def remove_entry(self, command: str, scope: str | None = None) -> bool:
        if scope is None:
            removed = False
            for scope_list in self._permissions.values():
                before = len(scope_list)
                scope_list[:] = [e for e in scope_list if e.get("command") != command]
                if len(scope_list) < before:
                    removed = True
            return removed
        scope_list = self._permissions.get(scope, [])
        before = len(scope_list)
        scope_list[:] = [e for e in scope_list if e.get("command") != command]
        return len(scope_list) < before

    def list_entries(self, scope: str | None = None) -> list[AllowlistEntry]:
        result = []
        scopes = (
            self._permissions.values() if scope is None
            else [self._permissions.get(scope, [])]
        )
        for scope_entries in scopes:
            for e in scope_entries:
                result.append(AllowlistEntry(
                    command=e.get("command", ""),
                    scope=e.get("scope", ""),
                    reason=e.get("reason", ""),
                    added_at=e.get("added_at", ""),
                ))
        return result

    def to_dict(self) -> dict:
        return self._permissions

    def save_to_baseline(self, layout: "Layout") -> None:
        from ..store import atomic_write, read_json
        baseline: dict = {}
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass
        baseline["exec_allowlist"] = self._permissions
        atomic_write(layout.baseline, baseline)


# ---------------------------------------------------------------------------
# Runtime allowlist gates
# ---------------------------------------------------------------------------

def maybe_prompt_shell_allowlist(
    layout: "Layout",
    entry: dict[str, Any],
    manifest: dict[str, Any],
    params: dict[str, Any],
    timeout: int,
    output: str,
) -> str:
    """Intercept shell_run 'command not in allowlist' errors and offer approval."""
    try:
        result = json.loads(output)
    except Exception:
        return output

    error = result.get("error", "")
    if not error.startswith("command not in allowlist:"):
        return output

    command = str(params.get("command", "")).strip()

    decision = request_approval(
        layout,
        subject="shell_run",
        detail=command,
        prompt="Allow this command?",
        options=("allow_once", "allow_always", "deny"),
        notification_severity="shell_run_blocked",
        notification_payload={
            "message": "Command blocked in autonomous session (auto:session)",
            "command": command,
            "context": "auto:session",
            "timestamp": time.time(),
            "note": "Operator can approve in main:session if needed",
        },
    )

    if decision == ApprovalDecision.DENY:
        return output

    if decision == ApprovalDecision.ALLOW_ALWAYS:
        shell_allowlist_add(layout, command)
    elif decision == ApprovalDecision.ALLOW_ONCE:
        os.environ["FCP_SHELL_RUN_ALLOW_ONCE"] = command
        try:
            from .dispatch import _run_skill
            return _run_skill(layout, entry, manifest, dict(params), timeout)
        finally:
            os.environ.pop("FCP_SHELL_RUN_ALLOW_ONCE", None)

    try:
        from .dispatch import _run_skill, _load_manifest
        new_manifest = _load_manifest(layout, entry)
        return _run_skill(layout, entry, new_manifest, params, timeout)
    except Exception:
        return output


def maybe_prompt_web_allowlist(
    layout: "Layout",
    entry: dict[str, Any],
    manifest: dict[str, Any],
    params: dict[str, Any],
    timeout: int,
    output: str,
) -> str:
    """Intercept web_fetch 'URL not in allowlist' errors and offer approval."""
    try:
        result = json.loads(output)
    except Exception:
        return output

    error = result.get("error", "")
    if not error.startswith("URL not in allowlist:"):
        return output

    url = str(params.get("url", "")).strip()

    decision = request_approval(
        layout,
        subject="web_fetch",
        detail=url,
        prompt="Allow this URL?",
        options=("allow_once", "allow_always", "deny"),
        notification_severity="web_fetch_blocked",
        notification_payload={
            "message": "URL blocked in autonomous session (auto:session)",
            "url": url,
            "context": "auto:session",
            "timestamp": time.time(),
            "note": "Operator can approve in main:session if needed",
        },
    )

    if decision == ApprovalDecision.DENY:
        return output

    if decision == ApprovalDecision.ALLOW_ALWAYS:
        web_allowlist_add(layout, url)
    elif decision == ApprovalDecision.ALLOW_ONCE:
        os.environ["FCP_WEB_FETCH_ALLOW_ONCE"] = url
        try:
            from .dispatch import _run_skill
            return _run_skill(layout, entry, manifest, params, timeout)
        finally:
            os.environ.pop("FCP_WEB_FETCH_ALLOW_ONCE", None)

    try:
        from .dispatch import _run_skill, _load_manifest
        new_manifest = _load_manifest(layout, entry)
        return _run_skill(layout, entry, new_manifest, params, timeout)
    except Exception:
        return output


# ---------------------------------------------------------------------------
# Manifest writers
# ---------------------------------------------------------------------------

def web_allowlist_add(layout: "Layout", url: str) -> None:
    """Append a URL prefix to web_fetch/manifest.json allowlist."""
    manifest_path = layout.skills_lib_dir / "web_fetch" / "manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        prefix = f"{parsed.scheme}://{parsed.netloc}/"
    except Exception:
        prefix = url

    allowlist: list[str] = manifest.get("allowlist", [])
    if prefix in allowlist:
        return

    allowlist.append(prefix)
    manifest["allowlist"] = allowlist
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, manifest_path)
    ui.print_ok(f"[web_fetch] '{prefix}' added to allowlist.")


def shell_allowlist_add(layout: "Layout", command: str) -> None:
    """Append a composite entry to shell_run/manifest.json allowlist_composite."""
    manifest_path = layout.skills_lib_dir / "shell_run" / "manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return

    composite: list[dict] = manifest.get("allowlist_composite", [])
    if any(e.get("command") == command for e in composite):
        return

    composite.append({"command": command})
    manifest["allowlist_composite"] = composite
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp, manifest_path)
    ui.print_ok(f"[shell_run] '{command}' added to allowlist_composite.")
