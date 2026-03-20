"""
Execution Permissions — FCP §10.

Manages allowlists and permissions for tool execution across different scopes:
  • shell_run: composite shell commands (dangerous operations)
  • file_ops: file read/write/delete (future)
  • system_ops: system-level operations (future)

Permissions are stored in baseline.exec_allowlist and loaded on-demand.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import Layout


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
        """Convert to dict for JSON serialization."""
        return {
            "command": self.command,
            "scope": self.scope,
            "reason": self.reason,
            "added_at": self.added_at or "",
        }


class ExecutionPermissions:
    """Manage execution permissions and allowlists."""

    def __init__(self, permissions_dict: dict | None = None):
        """Initialize from a permissions dict (baseline.exec_allowlist structure)."""
        self._permissions: dict[str, list[dict]] = permissions_dict or {}

    @staticmethod
    def load_from_baseline(layout: Layout) -> ExecutionPermissions:
        """Load permissions from baseline.json."""
        from .store import read_json

        baseline = {}
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass

        permissions_dict = baseline.get("exec_allowlist", {})
        return ExecutionPermissions(permissions_dict)

    def has_permission(self, command: str, scope: str) -> bool:
        """Check if a command is allowed in a given scope."""
        scope_list = self._permissions.get(scope, [])
        return any(e.get("command") == command for e in scope_list)

    def add_entry(
        self, command: str, scope: str, reason: str = ""
    ) -> None:
        """Add an entry to the allowlist."""
        if not isinstance(scope, str):
            scope = scope.value

        scope_list = self._permissions.setdefault(scope, [])

        # Check if already exists
        if any(e.get("command") == command for e in scope_list):
            return

        # Add new entry
        entry = AllowlistEntry(
            command=command,
            scope=scope,
            reason=reason,
            added_at=str(int(time.time())),
        )
        scope_list.append(entry.to_dict())

    def remove_entry(self, command: str, scope: str | None = None) -> bool:
        """Remove an entry by command (and optionally scope). Returns True if removed."""
        if scope is None:
            # Remove from all scopes
            removed = False
            for scope_list in self._permissions.values():
                before = len(scope_list)
                scope_list[:] = [e for e in scope_list if e.get("command") != command]
                if len(scope_list) < before:
                    removed = True
            return removed
        else:
            # Remove from specific scope
            scope_list = self._permissions.get(scope, [])
            before = len(scope_list)
            scope_list[:] = [e for e in scope_list if e.get("command") != command]
            return len(scope_list) < before

    def list_entries(self, scope: str | None = None) -> list[AllowlistEntry]:
        """List all entries (optionally filtered by scope)."""
        result = []
        if scope is None:
            # All entries
            for scope_entries in self._permissions.values():
                for e in scope_entries:
                    result.append(
                        AllowlistEntry(
                            command=e.get("command", ""),
                            scope=e.get("scope", ""),
                            reason=e.get("reason", ""),
                            added_at=e.get("added_at", ""),
                        )
                    )
        else:
            # Entries in specific scope
            scope_entries = self._permissions.get(scope, [])
            for e in scope_entries:
                result.append(
                    AllowlistEntry(
                        command=e.get("command", ""),
                        scope=e.get("scope", ""),
                        reason=e.get("reason", ""),
                        added_at=e.get("added_at", ""),
                    )
                )
        return result

    def to_dict(self) -> dict:
        """Return as dict for saving to baseline."""
        return self._permissions

    def save_to_baseline(self, layout: Layout) -> None:
        """Save permissions back to baseline.json."""
        from .store import atomic_write, read_json

        baseline = {}
        try:
            baseline = read_json(layout.baseline)
        except Exception:
            pass

        baseline["exec_allowlist"] = self._permissions
        atomic_write(layout.baseline, baseline)
