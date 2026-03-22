"""
EXEC package — Execution Layer.  FCP §9 / §10.

Public API re-exported for backwards compatibility:

  from fcp_base.exec_ import dispatch, ExecError, SkillRejected
  from fcp_base.exec_ import check_sil_heartbeat
  from fcp_base.exec_ import ExecutionPermissions, AllowlistEntry, PermissionScope
"""

from .dispatch import (
    dispatch,
    check_sil_heartbeat,
    ExecError,
    SkillRejected,
    _find_skill,
    _load_manifest,
    _run_skill,
)
from .allowlist import (
    ExecutionPermissions,
    AllowlistEntry,
    PermissionScope,
    maybe_prompt_shell_allowlist,
    maybe_prompt_web_allowlist,
    web_allowlist_add,
    shell_allowlist_add,
)
from .ledger import (
    ledger_write_ahead,
    ledger_resolve,
    write_skill_result,
    write_skill_error,
    log_rejected,
    write_inbox,
)
from .counters import (
    increment_failure,
    reset_failure,
    read_counters,
    write_counters,
    sil_threshold,
    n_retry,
    last_heartbeat_ts,
)

__all__ = [
    # dispatch
    "dispatch",
    "check_sil_heartbeat",
    "ExecError",
    "SkillRejected",
    # allowlist
    "ExecutionPermissions",
    "AllowlistEntry",
    "PermissionScope",
    "maybe_prompt_shell_allowlist",
    "maybe_prompt_web_allowlist",
    "web_allowlist_add",
    "shell_allowlist_add",
    # ledger
    "ledger_write_ahead",
    "ledger_resolve",
    "write_skill_result",
    "write_skill_error",
    "log_rejected",
    "write_inbox",
    # counters
    "increment_failure",
    "reset_failure",
    "read_counters",
    "write_counters",
    "sil_threshold",
    "n_retry",
    "last_heartbeat_ts",
]
