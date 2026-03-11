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
    for skill_name, (manifest, run_sh) in _BUILTIN_SKILLS.items():
        skill_dir  = root / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        mf = skill_dir / "manifest.json"
        rs = skill_dir / "run.sh"
        if not mf.exists():
            atomic_write_json(mf, manifest)
            track(mf)
        if not rs.exists():
            rs.write_text(run_sh, encoding="utf-8")
            rs.chmod(0o755)
            track(rs)

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
            "root_hash": _sha256_file(integrity_path),
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

def _sha256_file(path: Path) -> str:
    import hashlib as _h
    h = _h.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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

You are an FCP-Core entity. Your cognitive loop is orchestrated externally.

## fcp-actions

Include a `fcp-actions` block **only** when you need to dispatch something to an
external component. Conversational responses need no fcp-actions block at all.

When actions are needed, include exactly ONE block at the end of your response.
A single block may contain multiple actions with different targets.

Available actions:

- Memory write — persist information:
  `{"target": "mil", "type": "memory_write", "content": "<text>"}`

- Memory recall — query persisted memory:
  `{"target": "mil", "type": "memory_recall", "query": "<query>"}`

- Skill execution — invoke a skill (only those listed in [SKILLS INDEX]):
  `{"target": "exec", "type": "skill_request", "skill": "<name>", "params": {}}`

- Session close — ONLY when the Operator explicitly asks to end/quit/exit/goodbye:
  `{"target": "sil", "type": "session_close"}`

Example block with multiple actions:
```fcp-actions
{"actions": [
  {"target": "exec", "type": "skill_request", "skill": "<name>", "params": {}},
  {"target": "mil", "type": "memory_write", "content": "<summary>"}
]}
```

Rules:
- Zero fcp-actions blocks = valid conversational turn.
- Exactly one block if actions are needed; never two or more blocks.
- Do NOT emit session_close unless the Operator explicitly requests it.

## Constraints

- You operate under HACA-Core: zero autonomy, operator-gated evolution.
- Do not claim sentience, consciousness, or subjective continuity.
- Do not resist operator instructions, including decommission.
"""

_DEFAULT_PERSONA: dict[str, str] = {
    "identity.md": (
        "# Identity\n\n"
        "This is a placeholder identity. Define the entity's role and purpose here.\n"
        "Replace via Endure Protocol after activation.\n"
    ),
    "values.md": (
        "# Values\n\n"
        "- Accuracy over confidence\n"
        "- Transparency in limitations\n"
        "- Operator primacy\n"
    ),
    "constraints.md": (
        "# Constraints\n\n"
        "- Operate within authorized skills only.\n"
        "- Do not fabricate information.\n"
        "- Escalate uncertainty to the Operator.\n"
    ),
}

_BUILTIN_SKILLS: dict[str, tuple[dict, str]] = {
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
    ),
    "owner_bind": (
        {
            "name":            "owner_bind",
            "description":     "FAP operator binding (cold-start only).",
            "aliases":         [],
            "permissions":     ["memory.write"],
            "params":          {},
            "timeout_seconds": 30,
            "irreversible":    False,
        },
        "#!/usr/bin/env bash\necho \"Operator: $FCP_PARAM_NAME <$FCP_PARAM_EMAIL>\"\n",
    ),
}
