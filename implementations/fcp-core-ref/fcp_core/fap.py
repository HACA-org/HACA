"""
First Activation Protocol.  §4

Executes once on cold-start (absence of memory/imprint.json).
Transforms a pre-installed structural baseline into a live entity.

Pipeline:
  1. Structural validation
  2. Host environment capture (CPE topology check)
  3. Operator Channel initialization
  4. Operator enrollment
  5. Integrity Document generated
  6. Imprint Record finalized → written to memory/imprint.json
  7. Genesis Omega derived → written as genesis entry in integrity_chain.jsonl
  8. First session token issued

Atomicity: if any step raises FAPError, all writes produced so far are
reverted and memory/imprint.json is not created.  FAP re-executes on the
next boot.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .formats import (
    ChainEntry,
    ChainEntryType,
    ImprintRecord,
    OperatorBound,
    StructuralBaseline,
)
from .sil import (
    activate_beacon,
    build_skill_index,
    compute_integrity_files,
    issue_session_token,
    operator_channel_available,
    sha256_bytes,
    sha256_str,
    write_chain_entry,
    write_integrity_doc,
)
from .store import Layout, atomic_write, read_json

# HACA spec versions this implementation targets.
_HACA_ARCH_VERSION = "1.0.0"
_HACA_PROFILE = "HACA-Core-1.0.0"


class FAPError(Exception):
    """Raised when any FAP step fails.  Triggers rollback."""


def run(layout: Layout) -> str:
    """Execute the FAP pipeline.  Returns the new session_id on success.

    Raises FAPError if any step cannot complete.  All filesystem writes
    produced during the attempt are reverted before raising.
    """
    written: list[Path] = []

    try:
        # ------------------------------------------------------------------
        # Step 1 — Structural validation
        # ------------------------------------------------------------------
        _validate_structural_baseline(layout)

        # ------------------------------------------------------------------
        # Step 2 — Host environment capture (topology check)
        # ------------------------------------------------------------------
        baseline = StructuralBaseline.from_dict(read_json(layout.baseline))
        if baseline.cpe.topology != "transparent":
            raise FAPError(
                f"FAP step 2: CPE topology must be 'transparent', "
                f"got '{baseline.cpe.topology}'"
            )

        # ------------------------------------------------------------------
        # Step 3 — Operator Channel initialization
        # ------------------------------------------------------------------
        notif_ok, terminal_ok = operator_channel_available(layout)
        if not notif_ok:
            raise FAPError(
                "FAP step 3: operator_notifications/ is not writable"
            )
        if not terminal_ok:
            raise FAPError(
                "FAP step 3: terminal prompt is not available"
            )

        # ------------------------------------------------------------------
        # Step 4 — Operator enrollment
        # ------------------------------------------------------------------
        operator_name, operator_email = _enroll_operator()
        operator_hash = sha256_str(f"{operator_name}\n{operator_email}")
        operator_bound = OperatorBound(
            name=operator_name,
            email=operator_email,
            operator_hash=operator_hash,
        )

        # ------------------------------------------------------------------
        # Step 5 — Skill Index + Integrity Document
        # ------------------------------------------------------------------
        build_skill_index(layout)
        written.append(layout.skills_index)

        files = compute_integrity_files(layout)
        write_integrity_doc(layout, files)
        written.append(layout.integrity_doc)

        # ------------------------------------------------------------------
        # Step 6 — Imprint Record
        # ------------------------------------------------------------------
        integrity_doc_hash = sha256_str(
            json.dumps(read_json(layout.integrity_doc), separators=(",", ":"))
        )
        baseline_hash = sha256_str(
            json.dumps(read_json(layout.baseline), separators=(",", ":"))
        )
        skills_index_hash = sha256_str(
            json.dumps(read_json(layout.skills_index), separators=(",", ":"))
        )

        activated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        imprint = ImprintRecord(
            version="1.0",
            activated_at=activated_at,
            haca_arch_version=_HACA_ARCH_VERSION,
            haca_profile=_HACA_PROFILE,
            operator_bound=operator_bound,
            structural_baseline=baseline_hash,
            integrity_document=integrity_doc_hash,
            skills_index=skills_index_hash,
        )
        atomic_write(layout.imprint, imprint.to_dict())
        written.append(layout.imprint)

        # ------------------------------------------------------------------
        # Step 7 — Genesis Omega
        # ------------------------------------------------------------------
        imprint_raw = json.dumps(imprint.to_dict(), separators=(",", ":"))
        genesis_omega = sha256_str(imprint_raw)

        genesis_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        genesis = ChainEntry(
            seq=1,
            type=ChainEntryType.GENESIS,
            ts=genesis_ts,
            prev_hash=None,
            imprint_hash=genesis_omega,
        )
        write_chain_entry(layout, genesis)
        written.append(layout.integrity_chain)

        # ------------------------------------------------------------------
        # Step 8 — First session token
        # ------------------------------------------------------------------
        session_id = issue_session_token(layout)
        written.append(layout.session_token)

        # ------------------------------------------------------------------
        # Step 9 — First stimuli: onboarding message for the CPE
        # ------------------------------------------------------------------
        atomic_write(layout.first_stimuli, {
            "source": "fap",
            "message": (
                "[FIRST SESSION] You have just been activated for the first time. "
                "Begin by introducing yourself to the Operator: your name, your profile (HACA-Core), "
                "your available skills, and your operational boundaries (including what requires "
                "Operator authorization).\n\n"
                "Then ask the Operator for the following information to personalize your collaboration:\n"
                "- Preferred language for communication\n"
                "- Area of work or project context\n"
                "- Preferred communication style (concise, detailed, formal, informal)\n"
                "- Any other preferences or constraints you should know\n\n"
                "Save everything the Operator shares in structured memory "
                "(slugs: operator-profile, session-preferences)."
            ),
        })
        written.append(layout.first_stimuli)

        return session_id

    except FAPError:
        _rollback(written)
        raise
    except Exception as exc:
        _rollback(written)
        raise FAPError(f"FAP unexpected error: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_structural_baseline(layout: Layout) -> None:
    """Step 1: verify pre-installed structural files are present and parseable."""
    if not layout.boot_md.exists():
        raise FAPError("FAP step 1: boot.md is missing")

    if not layout.baseline.exists():
        raise FAPError("FAP step 1: state/baseline.json is missing")

    try:
        StructuralBaseline.from_dict(read_json(layout.baseline))
    except (KeyError, TypeError, ValueError) as exc:
        raise FAPError(f"FAP step 1: state/baseline.json is invalid: {exc}") from exc

    if not layout.persona_dir.is_dir():
        raise FAPError("FAP step 1: persona/ directory is missing")

    persona_files = list(layout.persona_dir.iterdir())
    if not persona_files:
        raise FAPError("FAP step 1: persona/ directory is empty")


def _enroll_operator() -> tuple[str, str]:
    """Step 4: interactive Operator enrollment via terminal prompt."""
    print("\n=== FCP-Core First Activation ===")
    print("This entity has not been activated yet.")
    print("Please provide the Operator details to bind this entity.\n")

    while True:
        name = input("Operator name: ").strip()
        if name:
            break
        print("Name cannot be empty.")

    while True:
        email = input("Operator email: ").strip()
        if email:
            break
        print("Email cannot be empty.")

    print(f"\nOperator bound: {name} <{email}>")
    confirm = input("Confirm? [y/N] ").strip().lower()
    if confirm != "y":
        raise FAPError("FAP step 4: Operator enrollment cancelled")

    return name, email


def _rollback(written: list[Path]) -> None:
    """Remove all files written during a failed FAP attempt."""
    for path in written:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
