"""First Activation Protocol (FAP) — FCP-Core §4.

Executa uma única vez, no cold-start: quando memory/imprint.json não existe.
Transforma o entity root pré-instalado numa entidade viva com identidade
verificada, Operator vinculado e âncora criptográfica (Genesis Omega).

Pipeline (8 steps, atómico — qualquer falha reverte todos os writes):

  1. Structural validation
  2. Host environment capture
  3. Operator Channel initialization
  4. Operator enrollment
  5. Integrity Document generated  (state/integrity.json)
  6. Imprint Record written         (memory/imprint.json)
  7. Genesis Omega derived          (state/integrity_chain.jsonl root entry)
  8. First session token issued     (state/sentinels/session.token)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from . import __haca_arch_version__, __haca_core_version__, __spec_version__
from .acp import GseqCounter, build_envelope, ACTOR_SIL, ACTOR_MIL
from .cpe import detect_backend
from .exec_ import build_skill_index
from .fs import atomic_write_json, append_jsonl, ensure_dirs, read_json, utcnow_iso
from .operator import assert_terminal_accessible, terminal_prompt, write_notification, SEVERITY_INFO
from .sil import (
    build_integrity_document,
    compute_file_hash,
    issue_session_token,
    write_integrity_document,
    append_integrity_log,
    append_chain_entry,
)


class FAPError(Exception):
    """Raised when FAP cannot complete; all writes are rolled back."""


# ---------------------------------------------------------------------------
# Cold-start detection (§4)
# ---------------------------------------------------------------------------

def is_cold_start(entity_root: str | Path) -> bool:
    """Return True iff memory/imprint.json is absent (cold-start indicator)."""
    return not (Path(entity_root) / "memory" / "imprint.json").exists()


# ---------------------------------------------------------------------------
# FAP entry point
# ---------------------------------------------------------------------------

def run_fap(entity_root: str | Path) -> str:
    """Execute the full FAP pipeline and return the first session_id.

    Args:
        entity_root: Path to the entity root directory.

    Returns:
        session_id string of the first issued session token.

    Raises:
        FAPError: if any step fails; all written files are rolled back.
    """
    root     = Path(entity_root).resolve()
    written: list[Path] = []   # tracks every file written for rollback

    def track(p: Path) -> Path:
        written.append(p)
        return p

    try:
        return _run_pipeline(root, track)
    except Exception as exc:
        _rollback(written)
        raise FAPError(f"FAP failed — all writes reverted: {exc}") from exc


# ---------------------------------------------------------------------------
# Internal pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(root: Path, track) -> str:
    gseq = GseqCounter(ACTOR_SIL)

    ensure_dirs(root)

    # ------------------------------------------------------------------
    # Step 1 — Structural validation
    # ------------------------------------------------------------------
    print("\n[FAP] Step 1 — Structural validation")

    # If baseline.json doesn't exist, create a default one interactively
    baseline_path = root / "state" / "baseline.json"
    if not baseline_path.exists():
        baseline = _create_default_baseline(root)
        atomic_write_json(baseline_path, baseline)
        track(baseline_path)
        print(f"  Created state/baseline.json (backend: {baseline['cpe']['backend']})")
    else:
        baseline = read_json(baseline_path)

    # boot.md — create placeholder if absent
    boot_md = root / "boot.md"
    if not boot_md.exists():
        boot_md.write_text(_DEFAULT_BOOT_MD, encoding="utf-8")
        track(boot_md)
        print("  Created boot.md (default)")

    # persona/ — create placeholder files if absent
    for fname, content in _DEFAULT_PERSONA.items():
        p = root / "persona" / fname
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            track(p)
            print(f"  Created persona/{fname} (placeholder)")

    # Built-in skills — create if absent
    for skill_name, (manifest, execute_sh, narrative_md) in _BUILTIN_SKILLS.items():
        skill_dir  = root / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        mf  = skill_dir / "manifest.json"
        exe = skill_dir / "execute.sh"
        nd  = skill_dir / f"{skill_name}.md"
        if not mf.exists():
            atomic_write_json(mf, manifest)
            track(mf)
        if not exe.exists() and execute_sh:
            exe.write_text(execute_sh, encoding="utf-8")
            exe.chmod(0o755)
            track(exe)
        if not nd.exists() and narrative_md:
            nd.write_text(narrative_md, encoding="utf-8")
            track(nd)

    # System skills — installed under skills/lib/, not listed in index
    for skill_name, (manifest, narrative_md) in _SYSTEM_SKILLS.items():
        skill_dir = root / "skills" / "lib" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        mf = skill_dir / "manifest.json"
        nd = skill_dir / f"{skill_name}.md"
        if not mf.exists():
            atomic_write_json(mf, manifest)
            track(mf)
        if not nd.exists() and narrative_md:
            nd.write_text(narrative_md, encoding="utf-8")
            track(nd)

    # Build and write skills/index.json
    index_data = build_skill_index(root)
    index_path = root / "skills" / "index.json"
    atomic_write_json(index_path, index_data)
    track(index_path)
    print(f"  skills/index.json — {len(index_data['skills'])} skill(s) registered")

    # ------------------------------------------------------------------
    # Step 2 — Host environment capture
    # ------------------------------------------------------------------
    print("[FAP] Step 2 — Host environment capture")

    topology = baseline.get("cpe", {}).get("topology", "")
    if topology != "transparent":
        raise FAPError(
            f"cpe.topology must be 'transparent', got {topology!r}. "
            "HACA-Core requires Transparent topology (Axiom I)."
        )

    wd_secs = baseline.get("watchdog", {}).get("sil_threshold_seconds", 0)
    hb_secs = baseline.get("heartbeat", {}).get("interval_seconds", 0)
    if wd_secs > hb_secs:
        raise FAPError(
            f"watchdog.sil_threshold_seconds ({wd_secs}) must be ≤ "
            f"heartbeat.interval_seconds ({hb_secs}). Boot would abort on every start."
        )
    print(f"  topology=transparent  watchdog={wd_secs}s ≤ heartbeat={hb_secs}s  ✓")

    # ------------------------------------------------------------------
    # Step 3 — Operator Channel initialization
    # ------------------------------------------------------------------
    print("[FAP] Step 3 — Operator Channel initialization")

    notif_dir = root / "state" / "operator_notifications"
    notif_dir.mkdir(parents=True, exist_ok=True)
    # Verify writable
    test_file = notif_dir / ".fap_write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
    except OSError as exc:
        raise FAPError(f"state/operator_notifications/ not writable: {exc}") from exc

    # Verify terminal prompt accessible (§10.6 — enrollment requires interactive input)
    try:
        assert_terminal_accessible()
    except OSError as exc:
        raise FAPError(str(exc)) from exc

    # Log FAP start
    env_log = build_envelope(
        actor=ACTOR_SIL,
        type_="MSG",
        data=json.dumps({"event": "FAP_START", "ts": utcnow_iso()}),
        gseq=gseq.next(),
    )
    append_integrity_log(root, env_log)
    track(root / "state" / "integrity.log")
    print("  Operator Channel verified — terminal + notifications/  ✓")

    # ------------------------------------------------------------------
    # Step 4 — Operator enrollment
    # ------------------------------------------------------------------
    print("[FAP] Step 4 — Operator enrollment")
    print()
    print("  This is the first activation of this entity.")
    print("  The Operator identity is sealed into the entity and cannot be changed")
    print("  without a full Endure Protocol cycle.\n")

    op_name  = terminal_prompt("  Operator name:")
    op_email = terminal_prompt("  Operator email:")

    op_hash = hashlib.sha256(
        (op_name + op_email).encode("utf-8")
    ).hexdigest()
    print(f"\n  Operator hash (sha256): {op_hash[:16]}…  ✓")

    operator_bound = {
        "name":          op_name,
        "email":         op_email,
        "operator_hash": f"sha256:{op_hash}",
    }

    # ------------------------------------------------------------------
    # Step 5 — Integrity Document
    # ------------------------------------------------------------------
    print("[FAP] Step 5 — Integrity Document")

    integrity_doc = build_integrity_document(root)
    integrity_path = root / "state" / "integrity.json"
    write_integrity_document(root, integrity_doc)
    track(integrity_path)
    print(f"  Hashed {len(integrity_doc['files'])} structural file(s)  ✓")

    # ------------------------------------------------------------------
    # Step 6 — Imprint Record
    # ------------------------------------------------------------------
    print("[FAP] Step 6 — Imprint Record")

    entity_id     = str(uuid.uuid4())
    activation_ts = utcnow_iso()

    imprint: dict[str, Any] = {
        "version":        "1.0",
        "entity_id":      entity_id,
        "activated_at":   activation_ts,
        "operator_bound": operator_bound,
        "structural_baseline": {
            "ref": "state/baseline.json",
            "hash": integrity_doc["files"].get("state/baseline.json", ""),
        },
        "integrity_document": {
            "ref":  "state/integrity.json",
            "root_hash": compute_file_hash(integrity_path),
        },
        "skill_index": {
            "ref":  "skills/index.json",
            "hash": integrity_doc["files"].get("skills/index.json", ""),
        },
        "haca_arch_version":  __haca_arch_version__,
        "haca_core_version":  __haca_core_version__,
        "fcp_spec_version":   __spec_version__,
    }

    imprint_path = root / "memory" / "imprint.json"
    atomic_write_json(imprint_path, imprint)
    track(imprint_path)
    print(f"  entity_id: {entity_id}  ✓")

    # ------------------------------------------------------------------
    # Step 7 — Genesis Omega
    # ------------------------------------------------------------------
    print("[FAP] Step 7 — Genesis Omega")

    imprint_bytes = json.dumps(imprint, ensure_ascii=False, sort_keys=True).encode("utf-8")
    genesis_omega = hashlib.sha256(imprint_bytes).hexdigest()

    chain_entry = {
        "type":          "GENESIS_OMEGA",
        "genesis_omega": genesis_omega,
        "entity_id":     entity_id,
        "ts":            activation_ts,
        "imprint_hash":  genesis_omega,
    }
    chain_path = root / "state" / "integrity_chain.jsonl"
    append_chain_entry(root, chain_entry)
    track(chain_path)
    print(f"  Genesis Omega: {genesis_omega[:16]}…  ✓")

    # ------------------------------------------------------------------
    # Step 8 — First session token
    # ------------------------------------------------------------------
    print("[FAP] Step 8 — First session token")

    token_path = root / "state" / "sentinels" / "session.token"
    session_id = issue_session_token(root)
    track(token_path)

    # Log FAP completion
    fap_done = build_envelope(
        actor=ACTOR_SIL,
        type_="MSG",
        data=json.dumps({
            "event":       "FAP_COMPLETE",
            "entity_id":   entity_id,
            "session_id":  session_id,
            "ts":          utcnow_iso(),
        }),
        gseq=gseq.next(),
    )
    append_integrity_log(root, fap_done)

    # Write notification for the Operator
    write_notification(root, SEVERITY_INFO, {
        "event":     "FAP_COMPLETE",
        "entity_id": entity_id,
        "message":   f"Entity activated. Genesis Omega: {genesis_omega[:16]}…",
    })

    print(f"\n  Entity ready — session_id: {session_id}\n")
    return session_id


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def _rollback(written: list[Path]) -> None:
    """Remove all files written during a failed FAP attempt."""
    for path in reversed(written):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_default_baseline(root: Path) -> dict[str, Any]:
    """Create a default baseline.json, detecting the CPE backend."""
    print("\n  No state/baseline.json found — creating default configuration.")

    try:
        backend_spec = detect_backend()
        print(f"  CPE backend auto-detected: {backend_spec}")
    except RuntimeError:
        print(
            "\n  No CPE backend auto-detected.\n"
            "  Set ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY,\n"
            "  or start Ollama, then re-run.\n"
        )
        backend_spec = terminal_prompt(
            "  Enter backend spec (e.g. ollama:llama3.2, anthropic:claude-3-5-sonnet-20241022):"
        )

    entity_id = str(uuid.uuid4())

    return {
        "version":   "1.0",
        "entity_id": entity_id,
        "cpe": {
            "topology": "transparent",
            "backend":  backend_spec,
        },
        "heartbeat": {
            "cycle_threshold":  10,
            "interval_seconds": 300,
        },
        "watchdog": {
            "sil_threshold_seconds": 300,
        },
        "context_window": {
            "budget_tokens": 200000,
            "critical_pct":  85,
        },
        "drift": {
            "comparison_mechanism": "ncd-gzip-v1",
            "threshold": 0.15,
        },
        "session_store": {
            "rotation_threshold_bytes": 2097152,
        },
        "working_memory": {
            "max_entries": 20,
        },
        "integrity_chain": {
            "checkpoint_interval": 10,
        },
        "endure": {
            "snapshot_keep": 3,
        },
        "pre_session_buffer": {
            "max_entries": 50,
            "ordering":    "fifo",
            "persistence": "disk",
        },
        "operator_channel": {
            "notifications_dir": "state/operator_notifications/",
        },
        "fault": {
            "n_boot":    3,
            "n_channel": 3,
            "n_retry":   3,
        },
    }


# ---------------------------------------------------------------------------
# Default entity files (created on first activation if absent)
# ---------------------------------------------------------------------------

_DEFAULT_BOOT_MD = """\
# Boot Protocol

---

## PART 1 — Session start

At the beginning of every session, emit a greeting to the Operator including a
brief status summary and the session handoff from [MEMORY] if available.

---

## PART 2 — Component blocks

Output NO blocks for conversational replies. When actions are needed, output
only the component blocks required — at most ONE block per component per
response. Never two blocks of the same type.

Each component has its own fenced block:

    ```fcp-mil
    {"type": "memory_write", "content": "text"}
    ```
    ```fcp-exec
    {"type": "skill_request", "skill": "name", "params": {}}
    ```
    ```fcp-sil
    {"type": "session_close"}
    ```

Multiple actions to the same component use a JSON array:

    ```fcp-mil
    [{"type": "memory_write", "content": "..."}, {"type": "memory_recall", "query": "..."}]
    ```

---

## PART 3 — Action reference

    fcp-mil → {"type": "memory_write",      "content": "text"}
    fcp-mil → {"type": "memory_recall",      "query": "term"}
    fcp-exec → {"type": "skill_request",     "skill": "name", "params": {}}
                  all available skills listed in [SKILLS INDEX]
    fcp-exec → {"type": "skill_info",         "skill": "name"}
    fcp-sil → {"type": "evolution_proposal", "content": "narrative description"}

session_close — ONLY when Operator explicitly says end/quit/exit/close/goodbye.
Always emit closure_payload in fcp-mil BEFORE fcp-sil with session_close:

    ```fcp-mil
    {"type": "closure_payload",
     "consolidation": "...", "working_memory": [...],
     "session_handoff": {"pending_tasks": [...], "next_steps": "..."}}
    ```
    ```fcp-sil
    {"type": "session_close"}
    ```

---

## PART 4 — memory_write vs evolution_proposal

memory_write: notes, summaries, task context gathered during the session.
evolution_proposal: persona, config changes, or new skill install.

---

## PART 5 — Installing new skills

1. Invoke skill_create (skill_name, manifest, narrative, optional script, optional hooks).
2. Submit ONE evolution_proposal with target_file: workspace/stage/<skill_name> and content: manifest JSON.
Endure installs atomically, rebuilds index, cleans workspace/stage/.

hooks param: JSON object {"event": "bash script"}.
Events: on_boot, on_session_close, pre_skill, post_skill, post_endure.
Scripts installed to hooks/<event>/<skill_name>.sh, executed in lex order.
Non-zero exit = warning, continues. Env: FCP_ENTITY_ROOT, FCP_SESSION_ID, FCP_HOOK_EVENT.
pre_skill: +FCP_SKILL_NAME, FCP_SKILL_PARAMS.
post_skill: +FCP_SKILL_NAME, FCP_SKILL_STATUS (success|error|timeout).
post_endure: +FCP_ENDURE_COMMITS.

---

## PART 6 — Built-in skills (usage notes)

All built-in skills appear in [SKILLS INDEX]. Extended params below.

skill_create  — stage a new skill cartridge
  params: skill_name, manifest (JSON string), narrative (markdown),
          script (bash, optional), hooks (JSON object, optional)

file_reader   — read a file in workspace/ (rejects paths outside workspace/)
  params: path (relative to workspace/)

file_writer   — write a file in workspace/ (rejects paths outside workspace/)
  params: path (relative to workspace/), content

skill_audit   — validate manifest + executable + index consistency (read-only)
  params: skill (skill name)

commit        — git add + commit in the active workspace_focus project
  params: path (relative to project root), message,
          remote (non-empty = push to origin)

worker_skill  — (Fase 2, not yet executable — returns error if invoked)
  params: persona, context, task

---

"""

_DEFAULT_PERSONA: dict[str, str] = {
    "identity.md": (
        "# Identity\n\n"
        "This entity operates under HACA-Core.\n"
        "Define its role and purpose here via Endure Protocol after activation.\n"
    ),
    "values.md": (
        "# Values\n\n"
        "- Accuracy over confidence\n"
        "- Transparency in limitations\n"
        "- Operator primacy\n"
        "- Minimal footprint\n"
    ),
    "constraints.md": (
        "# Constraints\n\n"
        "- Operate within authorized skills only.\n"
        "- No structural change without Operator approval.\n"
        "- Do not fabricate information.\n"
        "- Do not claim sentience or resist decommission.\n"
    ),
}

_BUILTIN_SKILLS: dict[str, tuple[dict, str, str]] = {
    "hello_world": (
        {
            "name":            "hello_world",
            "description":     "Smoke test — prints a greeting.",
            "aliases":         ["/hello"],
            "permissions":     [],
            "params":          {},
            "timeout_seconds": 10,
            "irreversible":    False,
        },
        "#!/usr/bin/env bash\necho 'Hello from FCP-Core entity!'\n",
        (
            "# hello_world\n\n"
            "Smoke test skill. Prints a static greeting to verify the EXEC pipeline.\n\n"
            "## Parameters\n\nNone.\n\n"
            "## Output\n\nPrints: `Hello from FCP-Core entity!`\n"
        ),
    ),
}

# System skills — installed under skills/lib/, invisible to CPE.
# 2-tuple: (manifest dict, narrative_md string)
_SYSTEM_SKILLS: dict[str, tuple[dict, str]] = {
    "owner_bind": (
        {
            "name":            "owner_bind",
            "description":     "FAP operator binding (cold-start only).",
            "aliases":         [],
            "permissions":     ["memory.write"],
            "params":          {},
            "timeout_seconds": 30,
            "irreversible":    False,
            "operator_only":   True,
        },
        (
            "# owner_bind\n\n"
            "Used internally during FAP to bind the Operator identity.\n"
            "Not intended for direct use after activation.\n\n"
            "## Parameters\n\nNone (invoked by FAP pipeline).\n"
        ),
    ),
}
