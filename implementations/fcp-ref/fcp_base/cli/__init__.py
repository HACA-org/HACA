"""
CLI package — FCP §12.1.

Public API re-exported for backwards compatibility.
The 'fcp' console script entry point calls fcp_base.cli:main.
"""

from .dispatch import main, _main, require_entity_root, print_help
from .ui import build_boot_stats, print_boot_header, print_block
from .init import run_init, read_fcp_version, write_entity_gitignore
from .commands import (
    run_normal,
    run_auto,
    run_auto_worker,
    run_update,
    run_doctor,
    run_decommission,
    run_model,
    run_status,
    run_agenda,
)
from .endure import run_endure_sync, run_endure_origin, run_endure_chain

__all__ = [
    "main",
    "build_boot_stats",
    "print_boot_header",
    "print_block",
    "run_init",
    "read_fcp_version",
    "write_entity_gitignore",
    "run_normal",
    "run_auto",
    "run_auto_worker",
    "run_update",
    "run_doctor",
    "run_decommission",
    "run_model",
    "run_status",
    "run_agenda",
    "run_endure_sync",
    "run_endure_origin",
    "run_endure_chain",
    "require_entity_root",
    "print_help",
]
