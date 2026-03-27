"""
SIL package — System Integrity Layer.  FCP §10.

Public API re-exported for backwards compatibility:

  from fcp_base.sil import write_notification, sha256_str, ...
"""

from .utils import utcnow, sha256_file, sha256_str, sha256_bytes
from .integrity import (
    tracked_files,
    compute_integrity_files,
    write_integrity_doc,
    verify_structural_files,
    verify_integrity_chain,
)
from .beacon import (
    activate_beacon,
    beacon_is_active,
    clear_beacon,
    issue_session_token,
    revoke_session_token,
    session_token_present,
    read_session_token,
)
from .chain import (
    _log_envelope,
    log_heartbeat,
    log_critical,
    log_severance_commit,
    log_cleared,
    log_sleep_complete,
    log_acp_envelope,
    write_evolution_auth,
    write_chain_entry,
    last_chain_seq,
    build_skill_index,
)
from .dispatch import (
    write_notification,
    operator_channel_available,
    stage_evolution_proposal,
)

__all__ = [
    # utils
    "utcnow",
    "sha256_file",
    "sha256_str",
    "sha256_bytes",
    # integrity
    "tracked_files",
    "compute_integrity_files",
    "write_integrity_doc",
    "verify_structural_files",
    "verify_integrity_chain",
    # beacon
    "activate_beacon",
    "beacon_is_active",
    "clear_beacon",
    "issue_session_token",
    "revoke_session_token",
    "session_token_present",
    "read_session_token",
    # chain
    "log_heartbeat",
    "log_critical",
    "log_severance_commit",
    "log_cleared",
    "log_sleep_complete",
    "log_acp_envelope",
    "write_evolution_auth",
    "write_chain_entry",
    "last_chain_seq",
    "build_skill_index",
    # dispatch
    "write_notification",
    "operator_channel_available",
    "stage_evolution_proposal",
]
