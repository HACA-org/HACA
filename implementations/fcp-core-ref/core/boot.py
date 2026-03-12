"""Boot Sequence — FCP-Core §5.

Pipeline determinístico com 8 fases (0-7). Cada fase deve completar antes
da próxima iniciar. Qualquer falha levanta BootError e nenhum session token
é emitido.

Retorna um BootContext com tudo o que o session loop precisa.
"""

from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from .acp import (
    GseqCounter, ACTOR_SIL, ACTOR_FCP, build_envelope,
    TYPE_CTX_SKIP, TYPE_CRITICAL_CLEARED, TYPE_ACTION_LEDGER,
)
from .cpe import CPEBackend
from .exec_ import ExecDispatcher, SkillIndex, load_skill_index
from .fs import read_json, read_jsonl, utcnow_iso, drain_presession
from .mil import (
    read_session_tail,
    load_active_context,
    load_session_handoff,
)
from .operator import (
    terminal_prompt, assert_terminal_accessible,
    write_notification, SEVERITY_DEGRADED,
)
from .sil import (
    activate_distress_beacon,
    append_integrity_log,
    check_distress_beacon,
    get_crash_counter,
    get_pending_proposals,
    get_unresolved_criticals,
    has_sleep_complete,
    has_unresolved_critical,
    issue_session_token,
    read_distress_beacon,
    record_crash_recovery,
    remove_session_token,
    read_session_token,
    verify_integrity_chain,
    verify_integrity_document,
    write_ctx_skip,
    write_evolution_auth,
    write_evolution_rejected,
    write_heartbeat,
    write_proposal_pending,
    write_sleep_complete,
)


class BootError(Exception):
    """Raised when a boot phase fails.  No session token is issued."""
    def __init__(self, phase: str, reason: str) -> None:
        self.phase  = phase
        self.reason = reason
        super().__init__(f"[Boot/{phase}] {reason}")


# ---------------------------------------------------------------------------
# Boot result
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class BootContext:
    session_id:       str
    entity_root:      Path
    baseline:         dict[str, Any]
    operator_name:    str
    cpe:              CPEBackend
    skill_index:      SkillIndex
    dispatcher:       ExecDispatcher
    assembled_context: str           # fully assembled CPE input for first cycle
    sil_gseq:         GseqCounter
    mil_gseq:         GseqCounter
    fcp_gseq:         GseqCounter
    exec_gseq:        GseqCounter


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_boot(entity_root: str | Path) -> BootContext:
    """Execute the full Boot Sequence and return a BootContext.

    Args:
        entity_root: Path to the (already FAP-initialised) entity root.

    Returns:
        BootContext ready for the session loop.

    Raises:
        BootError: if any phase fails.
    """
    root = Path(entity_root).resolve()

    sil_gseq  = GseqCounter(ACTOR_SIL)
    fcp_gseq  = GseqCounter(ACTOR_FCP)
    mil_gseq  = GseqCounter("mil")
    exec_gseq = GseqCounter("exec")

    # ------------------------------------------------------------------
    # Pre-phase: Passive Distress Beacon (§10.7)
    # ------------------------------------------------------------------
    if check_distress_beacon(root):
        beacon = read_distress_beacon(root) or {}
        reason = beacon.get("reason", "unknown")
        activated = beacon.get("activated_at", "?")
        print(f"\n[Boot/BEACON] Passive Distress Beacon is active.")
        print(f"  Activated: {activated}")
        print(f"  Reason:    {reason}")
        print(
            "\n  The entity is in suspended halt.  No session token will be issued.\n"
            "  Operator must clear the beacon after resolving the underlying cause.\n"
        )
        ans = terminal_prompt(
            "  Clear the beacon and proceed? [yes/no]",
            options=["yes", "no"],
        )
        if ans != "yes":
            raise BootError("BEACON", "Operator declined to clear beacon.")
        from .sil import clear_distress_beacon
        clear_distress_beacon(root)
        print("  Beacon cleared.  Proceeding with boot.\n")

    # ------------------------------------------------------------------
    # Phase 0 — Operator Bound + Operator Channel
    # ------------------------------------------------------------------
    imprint       = _load_imprint(root)  # raises BootError if invalid
    operator_name = imprint.get("operator_bound", {}).get("name", "")
    baseline = _load_baseline(root)

    notif_dir = root / "state" / "operator_notifications"
    notif_dir.mkdir(parents=True, exist_ok=True)
    test = notif_dir / ".boot_write_test"
    try:
        test.write_text("ok")
        test.unlink()
    except OSError as exc:
        raise BootError("0", f"state/operator_notifications/ not writable: {exc}")

    # Verify terminal prompt accessible (§10.6)
    try:
        assert_terminal_accessible()
    except OSError as exc:
        raise BootError("0", str(exc))

    # ------------------------------------------------------------------
    # Phase 1 — Host introspection
    # ------------------------------------------------------------------
    topology = baseline.get("cpe", {}).get("topology", "")
    if topology != "transparent":
        raise BootError(
            "1",
            f"cpe.topology must be 'transparent', got {topology!r}. "
            "No recovery path — entity cannot start in opaque topology."
        )

    wd_secs = baseline.get("watchdog", {}).get("sil_threshold_seconds", 0)
    hb_secs = baseline.get("heartbeat", {}).get("interval_seconds", 0)
    if wd_secs > hb_secs:
        raise BootError(
            "1",
            f"watchdog.sil_threshold_seconds ({wd_secs}) > "
            f"heartbeat.interval_seconds ({hb_secs}) — constraint violation."
        )

    # ------------------------------------------------------------------
    # Phase 2 — Crash Recovery
    # ------------------------------------------------------------------
    stale_token = read_session_token(root)
    if stale_token is not None:
        _handle_crash_recovery(root, stale_token, baseline, sil_gseq)

    # ------------------------------------------------------------------
    # Phase 3 — Integrity Verification
    # ------------------------------------------------------------------
    # Step 1: chain anchor
    ok, err = verify_integrity_chain(root)
    if not ok:
        raise BootError("3", f"Integrity Chain invalid: {err}")

    # Step 2: structural file hashes
    ok, errors = verify_integrity_document(root)
    if not ok:
        raise BootError("3", f"Integrity Document mismatch: {'; '.join(errors)}")

    # ------------------------------------------------------------------
    # Phase 4 — Skill Index
    # ------------------------------------------------------------------
    skill_index = load_skill_index(root)

    # ------------------------------------------------------------------
    # Phase 5 — Context Assembly (Boot Manifest)
    # ------------------------------------------------------------------
    budget_tokens = baseline.get("context_window", {}).get("budget_tokens", 200_000)
    # Rough approximation: 1 token ≈ 4 chars
    char_budget = budget_tokens * 4

    ctx_parts: list[str] = []

    # [PERSONA]
    persona_dir = root / "persona"
    if persona_dir.exists():
        for pf in sorted(persona_dir.glob("*.md")):
            content = pf.read_text(encoding="utf-8")
            ctx_parts.append(f"[PERSONA: {pf.name}]\n{content}")

    # [BOOT PROTOCOL]
    boot_md = root / "boot.md"
    if boot_md.exists():
        ctx_parts.append(f"[BOOT PROTOCOL]\n{boot_md.read_text(encoding='utf-8')}")

    # [SKILLS INDEX]
    skills_index_path = root / "skills" / "index.json"
    if skills_index_path.exists():
        index_raw = skills_index_path.read_text(encoding="utf-8")
        ctx_parts.append(f"[SKILLS INDEX]\n{index_raw}")

    # [SKILL:<name>] manifests
    skills_dir = root / "skills"
    if skills_dir.exists():
        for manifest_path in sorted(skills_dir.glob("*/manifest.json")):
            skill_name = manifest_path.parent.name
            ctx_parts.append(
                f"[SKILL:{skill_name}]\n{manifest_path.read_text(encoding='utf-8')}"
            )

    # [MEMORY] — active_context + session handoff (§5.1)
    # Working Memory is only trusted if the previous session closed cleanly.
    # Cross-reference against SLEEP_COMPLETE record before loading (§5.1).
    if has_sleep_complete(root):
        active  = load_active_context(root)
        handoff = load_session_handoff(root)
        for entry in active:
            ctx_parts.append(f"[MEMORY: {entry['path']}]\n{entry['content']}")
        if handoff:
            ctx_parts.append(
                f"[MEMORY: session-handoff]\n{json.dumps(handoff, indent=2)}"
            )
    else:
        # No clean Sleep Cycle record — discard Working Memory, log CTX_SKIP.
        wm_skip = build_envelope(
            actor=ACTOR_SIL,
            type_=TYPE_CTX_SKIP,
            data=json.dumps({
                "reason": "no_sleep_complete_record",
                "ts":     utcnow_iso(),
            }),
            gseq=sil_gseq.next(),
        )
        append_integrity_log(root, wm_skip)

    # [SESSION] — tail of session.jsonl, newest-first, budget-limited
    session_entries = read_session_tail(root, max_entries=200)
    if session_entries:
        session_text = "\n".join(
            json.dumps(e, ensure_ascii=False) for e in session_entries
        )
        ctx_parts.append(f"[SESSION]\n{session_text}")

    # [PRESESSION] — pre-session buffer, FIFO order, capacity-bounded (§8.3)
    max_ps     = baseline.get("pre_session_buffer", {}).get("max_entries")
    presession, n_ps_discarded = drain_presession(root, max_entries=max_ps)

    if n_ps_discarded:
        ps_skip = build_envelope(
            actor=ACTOR_SIL,
            type_=TYPE_CTX_SKIP,
            data=json.dumps({
                "reason":    "presession_buffer_overflow",
                "discarded": n_ps_discarded,
                "ts":        utcnow_iso(),
            }),
            gseq=sil_gseq.next(),
        )
        append_integrity_log(root, ps_skip)
        write_notification(root, SEVERITY_DEGRADED, {
            "event":     "PRESESSION_OVERFLOW",
            "discarded": n_ps_discarded,
        })

    if presession:
        presession_text = "\n".join(
            json.dumps(e, ensure_ascii=False) for e in presession
        )
        ctx_parts.append(f"[PRESESSION]\n{presession_text}")

    assembled_context = "\n\n---\n\n".join(ctx_parts)

    # ------------------------------------------------------------------
    # Phase 6 — Critical Condition Check + Pending Evolution Proposals
    # ------------------------------------------------------------------
    if has_unresolved_critical(root):
        unresolved = get_unresolved_criticals(root)
        print(f"\n[Boot/6] {len(unresolved)} unresolved Critical condition(s):")
        for crit in unresolved:
            print(f"  [{crit.get('type')}] tx={crit.get('tx', '?')[:8]}…  {crit.get('data', '')[:120]}")
        print()
        ans = terminal_prompt(
            "  Acknowledge and clear all Critical conditions to proceed? [yes/no]",
            options=["yes", "no"],
        )
        if ans != "yes":
            raise BootError("6", "Operator declined to acknowledge Critical conditions.")
        # Write CRITICAL_CLEARED for each
        for crit in unresolved:
            env = build_envelope(
                actor=ACTOR_SIL,
                type_=TYPE_CRITICAL_CLEARED,
                data=json.dumps({
                    "cleared_tx":  crit.get("tx", ""),
                    "cleared_by":  "operator",
                    "ts":          utcnow_iso(),
                }),
                gseq=sil_gseq.next(),
            )
            append_integrity_log(root, env)

    # Pending Evolution Proposals from previous sessions (§10.5)
    _review_pending_proposals(root, sil_gseq, operator_name)

    # ------------------------------------------------------------------
    # Phase 7 — Session Token Issuance
    # ------------------------------------------------------------------
    session_id = issue_session_token(root)
    write_heartbeat(root, sil_gseq, session_id)

    # Initialise EXEC dispatcher
    dispatcher = ExecDispatcher(root, skill_index, exec_gseq)

    return BootContext(
        session_id=session_id,
        entity_root=root,
        baseline=baseline,
        operator_name=operator_name,
        cpe=_init_cpe(baseline),
        skill_index=skill_index,
        dispatcher=dispatcher,
        assembled_context=assembled_context,
        sil_gseq=sil_gseq,
        mil_gseq=mil_gseq,
        fcp_gseq=fcp_gseq,
        exec_gseq=exec_gseq,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_imprint(root: Path) -> dict[str, Any]:
    imprint_path = root / "memory" / "imprint.json"
    if not imprint_path.exists():
        raise BootError("0", "memory/imprint.json absent — entity not initialised (FAP required).")
    try:
        data = read_json(imprint_path)
    except Exception as exc:
        raise BootError("0", f"memory/imprint.json malformed: {exc}") from exc
    ob = data.get("operator_bound", {})
    if not ob.get("name") or not ob.get("operator_hash"):
        raise BootError("0", "Operator Bound absent or malformed in imprint.json.")
    return data


def _review_pending_proposals(
    root:          Path,
    sil_gseq:      GseqCounter,
    operator_name: str,
) -> None:
    """Present pending Evolution Proposals from previous sessions (§10.5).

    Called during Phase 6.  Each proposal is shown via terminal prompt;
    the Operator approves or rejects.  Outcome written to integrity.log;
    never returned to the CPE.
    """
    pending = get_pending_proposals(root)
    if not pending:
        return

    print(f"\n[Boot/6] {len(pending)} pending Evolution Proposal(s) from previous session(s):")
    for i, entry in enumerate(pending, 1):
        try:
            d = json.loads(entry.get("data", "{}"))
        except Exception:
            d = {}
        content     = d.get("content", "(no content)")
        proposal_tx = d.get("proposal_tx", "?")
        print(f"\n  [{i}] tx={proposal_tx[:8]}…")
        print(f"  {content[:400]}")
        print()
        ans = terminal_prompt(
            "  Approve this Evolution Proposal? [yes/no]",
            options=["yes", "no"],
        )
        if ans == "yes":
            digest = hashlib.sha256(content.encode()).hexdigest()
            write_evolution_auth(root, sil_gseq, proposal_tx, digest, operator_name)
        else:
            write_evolution_rejected(root, sil_gseq, proposal_tx)
    print()


def _load_baseline(root: Path) -> dict[str, Any]:
    path = root / "state" / "baseline.json"
    if not path.exists():
        raise BootError("0", "state/baseline.json absent.")
    try:
        return read_json(path)
    except Exception as exc:
        raise BootError("0", f"state/baseline.json malformed: {exc}") from exc


def _init_cpe(baseline: dict[str, Any]) -> CPEBackend:
    backend_spec = baseline.get("cpe", {}).get("backend", "")
    if not backend_spec:
        raise BootError("1", "cpe.backend not declared in state/baseline.json.")
    try:
        return CPEBackend(backend_spec)
    except Exception as exc:
        raise BootError("1", f"CPE backend init failed ({backend_spec!r}): {exc}") from exc


def _handle_crash_recovery(
    root:       Path,
    token:      dict[str, Any],
    baseline:   dict[str, Any],
    sil_gseq:   GseqCounter,
) -> None:
    """Handle stale session token at boot (§5.2)."""
    print(
        f"\n[Boot/2] Stale session token detected "
        f"(session {token.get('session_id', '?')[:8]}…).\n"
        "  Previous Sleep Cycle did not complete.\n"
    )

    # Check consecutive crash counter
    crash_count = get_crash_counter(root) + 1
    record_crash_recovery(root, sil_gseq, f"Crash #{crash_count}")

    n_boot = baseline.get("fault", {}).get("n_boot", 3)
    if crash_count >= n_boot:
        activate_distress_beacon(
            root,
            f"Boot loop: {crash_count} consecutive crashes (threshold={n_boot})."
        )
        raise BootError(
            "2",
            f"Boot loop threshold reached ({crash_count} crashes). "
            "Passive Distress Beacon activated."
        )

    # Scan for unresolved ACTION_LEDGER entries
    entries = read_jsonl(root / "memory" / "session.jsonl")
    if entries:
        unresolved_ledger = [
            e for e in entries
            if e.get("type") == TYPE_ACTION_LEDGER
            and e.get("data", "")
            and json.loads(e.get("data", "{}")).get("status") == "in_progress"
        ]
        if unresolved_ledger:
            print(f"  {len(unresolved_ledger)} unresolved ACTION_LEDGER entr(y/ies) found:\n")
            for entry in unresolved_ledger:
                try:
                    d = json.loads(entry.get("data", "{}"))
                    print(f"    skill={d.get('skill','?')}  tx={entry.get('tx','?')[:8]}…")
                except Exception:
                    pass
            print(
                "\n  These are irreversible actions that may or may not have executed.\n"
                "  They will NOT be auto-retried.  Operator must decide.\n"
            )
            terminal_prompt(
                "  Acknowledged? Press Enter to continue.",
                options=None,
            )

    # Write SLEEP_COMPLETE stub so next boot is clean
    write_sleep_complete(root, sil_gseq, session_id=token.get("session_id", ""))
    remove_session_token(root)
    print(f"  Crash recovery complete (crash #{crash_count}).  Proceeding.\n")
