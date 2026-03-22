"""
Compliance checker — FCP §13.

Programmatically verifies the checkboxes that can be checked statically:
entity structure, integrity document, chain continuity, skills, session token.

Used by /doctor and the integration test suite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sil import sha256_file as _sha256_file, sha256_str as _sha256_str_prefixed
from .store import Layout, read_json, read_jsonl


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    section: str        # e.g. "§2.1", "§3.3", "§9.5"
    check: str          # short description
    passed: bool
    detail: str = ""


def _ok(section: str, check: str) -> Finding:
    return Finding(section=section, check=check, passed=True)


def _fail(section: str, check: str, detail: str = "") -> Finding:
    return Finding(section=section, check=check, passed=False, detail=detail)


# ---------------------------------------------------------------------------
# §2.1 — Entity structure
# ---------------------------------------------------------------------------

def check_structure(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    required_dirs = [
        ("boot.md",           False, "§2.1"),
        ("persona",           True,  "§2.1"),
        ("skills",            True,  "§2.1"),
        ("skills/lib",        True,  "§2.1"),
        ("hooks",             True,  "§2.1"),
        ("workspace",         True,  "§2.1"),
        ("workspace/stage",   True,  "§2.1"),
        ("io",                True,  "§2.1"),
        ("io/inbox",          True,  "§2.1"),
        ("io/inbox/presession", True, "§2.1"),
        ("io/spool",          True,  "§2.1"),
        ("memory",            True,  "§2.1"),
        ("memory/episodic",   True,  "§2.1"),
        ("memory/semantic",   True,  "§2.1"),
        ("memory/active_context", True, "§2.1"),
        ("state",             True,  "§2.1"),
        ("state/sentinels",   True,  "§2.1"),
        ("state/snapshots",   True,  "§2.1"),
        ("state/operator_notifications", True, "§2.1"),
    ]

    for rel, is_dir, sec in required_dirs:
        p = layout.root / rel
        if is_dir:
            if p.is_dir():
                findings.append(_ok(sec, f"{rel}/ exists"))
            else:
                findings.append(_fail(sec, f"{rel}/ exists", f"missing: {rel}"))
        else:
            if p.is_file():
                findings.append(_ok(sec, f"{rel} exists"))
            else:
                findings.append(_fail(sec, f"{rel} exists", f"missing: {rel}"))

    required_files = [
        ("memory/imprint.json",      "§3.13"),
        ("state/baseline.json",      "§3.2"),
        ("state/integrity.json",     "§3.3"),
        ("state/integrity_chain.jsonl", "§3.12"),
        ("skills/index.json",        "§3.9"),
    ]
    for rel, sec in required_files:
        p = layout.root / rel
        if p.is_file():
            findings.append(_ok(sec, f"{rel} exists"))
        else:
            findings.append(_fail(sec, f"{rel} exists", f"missing: {rel}"))

    return findings


# ---------------------------------------------------------------------------
# §3.3 — Integrity Document vs actual file hashes
# ---------------------------------------------------------------------------

def check_integrity(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    if not layout.integrity_doc.exists():
        return [_fail("§3.3", "integrity.json present", "missing")]

    try:
        doc = read_json(layout.integrity_doc)
    except Exception as exc:
        return [_fail("§3.3", "integrity.json parseable", str(exc))]

    tracked: dict[str, str] = doc.get("files", {})
    if not tracked:
        findings.append(_fail("§3.3", "integrity.json has tracked files", "files map empty"))
        return findings

    for rel, expected_hash in tracked.items():
        p = layout.root / rel
        if not p.exists():
            findings.append(_fail("§3.3", f"tracked file exists: {rel}", "absent"))
            continue
        actual = _sha256_file(p)
        if actual == expected_hash:
            findings.append(_ok("§3.3", f"hash match: {rel}"))
        else:
            findings.append(_fail("§3.3", f"hash match: {rel}",
                                  f"expected {expected_hash[:12]}… got {actual[:12]}…"))

    return findings


# ---------------------------------------------------------------------------
# §3.12 — Integrity Chain continuity
# ---------------------------------------------------------------------------

def check_chain(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    if not layout.integrity_chain.exists():
        return [_fail("§3.12", "integrity_chain.jsonl present", "missing")]

    lines = layout.integrity_chain.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [_fail("§3.12", "chain not empty", "no entries")]

    prev_hash = ""
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception as exc:
            findings.append(_fail("§3.12", f"chain entry {i} parseable", str(exc)))
            continue

        seq = entry.get("seq", i)

        # prev_hash continuity (skip genesis)
        if i > 0:
            declared_prev = entry.get("prev_hash", "")
            if declared_prev != prev_hash:
                findings.append(_fail(
                    "§3.12", f"chain entry {seq} prev_hash continuity",
                    f"expected {prev_hash[:12]}… got {declared_prev[:12]}…"
                ))
            else:
                findings.append(_ok("§3.12", f"chain entry {seq} prev_hash ok"))

        # ENDURE_COMMIT must have evolution_auth_digest
        entry_type = entry.get("type", "")
        if entry_type == "ENDURE_COMMIT":
            if entry.get("evolution_auth_digest"):
                findings.append(_ok("§3.12", f"ENDURE_COMMIT {seq} has auth_digest"))
            else:
                findings.append(_fail("§3.12", f"ENDURE_COMMIT {seq} has auth_digest",
                                      "missing evolution_auth_digest"))

        prev_hash = _sha256_str_prefixed(line)

    findings.append(_ok("§3.12", f"chain has {len(lines)} entries"))
    return findings


# ---------------------------------------------------------------------------
# §9.5 — Built-in skills present and valid
# ---------------------------------------------------------------------------

BUILTIN_SKILLS = [
    "skill_create", "skill_audit", "file_reader",
    "file_writer", "worker_skill", "shell_run", "web_fetch",
]

REQUIRED_MANIFEST_FIELDS = [
    "name", "version", "description", "timeout_seconds",
    "background", "irreversible", "class",
]


def check_skills(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    if not layout.skills_index.exists():
        return [_fail("§9.5", "skills/index.json present", "missing")]

    try:
        index = read_json(layout.skills_index)
    except Exception as exc:
        return [_fail("§9.5", "skills/index.json parseable", str(exc))]

    indexed_names = {s.get("name") for s in index.get("skills", [])}

    for name in BUILTIN_SKILLS:
        # check indexed
        if name in indexed_names:
            findings.append(_ok("§9.5", f"{name} in index"))
        else:
            findings.append(_fail("§9.5", f"{name} in index", "not found"))

        # check manifest
        manifest_path = layout.skills_lib_dir / name / "manifest.json"
        if not manifest_path.exists():
            findings.append(_fail("§9.5", f"{name} manifest exists", "missing"))
            continue
        try:
            manifest = read_json(manifest_path)
        except Exception as exc:
            findings.append(_fail("§9.5", f"{name} manifest parseable", str(exc)))
            continue
        for f in REQUIRED_MANIFEST_FIELDS:
            if f not in manifest:
                findings.append(_fail("§9.5", f"{name} manifest.{f}", "missing"))
            else:
                findings.append(_ok("§9.5", f"{name} manifest.{f}"))

        # check executable
        exe_found = any(
            (layout.skills_lib_dir / name / exe).exists()
            for exe in ("run.py", "run.sh", "run")
        )
        if exe_found:
            findings.append(_ok("§9.5", f"{name} executable exists"))
        else:
            findings.append(_fail("§9.5", f"{name} executable exists", "no run.py/run.sh/run"))

        # operator-class skills must not be in skills index visible block
        skill_class = manifest.get("class", "")
        if skill_class == "operator":
            findings.append(_ok("§9.5", f"{name} is operator-class (excluded from CPE)"))

    return findings


# ---------------------------------------------------------------------------
# §3.5 — Session token (SIL exclusive)
# ---------------------------------------------------------------------------

def check_session_token(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    token_path = layout.session_token
    if not token_path.exists():
        findings.append(_ok("§3.5", "session token absent (no active session)"))
        return findings

    try:
        token = read_json(token_path)
    except Exception as exc:
        findings.append(_fail("§3.5", "session token parseable", str(exc)))
        return findings

    for field in ("issued_at", "genesis_omega"):
        if field in token:
            findings.append(_ok("§3.5", f"session token has {field}"))
        else:
            findings.append(_fail("§3.5", f"session token has {field}", "missing"))

    revoked = "revoked_at" in token
    findings.append(_ok("§3.5", f"session token revoked={revoked}"))

    return findings


# ---------------------------------------------------------------------------
# §10 — Drift probes format
# ---------------------------------------------------------------------------

def check_drift_probes(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    if not layout.drift_probes.exists():
        findings.append(_ok("§10.2", "drift probes file absent (optional at genesis)"))
        return findings

    probes = read_jsonl(layout.drift_probes)
    for i, probe in enumerate(probes):
        for f in ("target", "reference", "type"):
            if f in probe:
                findings.append(_ok("§10.2", f"probe {i} has {f}"))
            else:
                findings.append(_fail("§10.2", f"probe {i} has {f}", "missing"))

    return findings


# ---------------------------------------------------------------------------
# §9.5 — Custom skills: zero-code requires README.md
# ---------------------------------------------------------------------------

def check_custom_skills(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    if not layout.skills_index.exists():
        return []

    try:
        index = read_json(layout.skills_index)
    except Exception:
        return []

    for entry in index.get("skills", []):
        if entry.get("class") not in ("custom", "user"):
            continue
        name = entry.get("name", "")
        skill_dir = layout.skills_dir / name
        has_exe = any((skill_dir / exe).exists() for exe in ("run.py", "run.sh", "run"))
        has_readme = (skill_dir / "README.md").exists()
        if has_exe:
            findings.append(_ok("§9.5", f"custom skill {name}: executable present"))
        elif has_readme:
            findings.append(_ok("§9.5", f"custom skill {name}: zero-code (README.md present)"))
        else:
            findings.append(_fail("§9.5", f"custom skill {name}: no executable or README.md",
                                  "skill is not callable"))

    return findings


# ---------------------------------------------------------------------------
# §10.4 — Severance pending (boot blocker)
# ---------------------------------------------------------------------------

def check_severance(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    if not layout.integrity_log.exists():
        return [_ok("§10.4", "no severance pending")]

    cleared_seqs: set[int] = set()
    severance_seqs: list[tuple[int, dict]] = []

    lines = [l.strip() for l in layout.integrity_log.read_text(encoding="utf-8").splitlines() if l.strip()]
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
            raw = rec.get("data", "{}")
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                continue
            dtype = data.get("type", "")
            if dtype == "SEVERANCE_COMMIT":
                severance_seqs.append((i + 1, data))
            elif dtype == "CRITICAL_CLEARED":
                try:
                    cleared_seqs.add(int(data.get("clears_seq", -1)))
                except Exception:
                    pass
        except Exception:
            continue

    pending = [(seq, d) for seq, d in severance_seqs if seq not in cleared_seqs]
    if not pending:
        findings.append(_ok("§10.4", "no severance pending"))
    else:
        for seq, data in pending:
            skill = data.get("skill", "unknown")
            findings.append(_fail("§10.4", f"SEVERANCE_PENDING: skill '{skill}' (seq {seq})",
                                  "boot will be blocked until Operator resolves via /endure"))

    return findings


# ---------------------------------------------------------------------------
# §6.4 — CMI configuration when CMI skills are active
# ---------------------------------------------------------------------------

def check_cmi(layout: Layout) -> list[Finding]:
    findings: list[Finding] = []

    if not layout.skills_index.exists():
        return []

    try:
        index = read_json(layout.skills_index)
    except Exception:
        return []

    cmi_skills = {"cmi_send", "cmi_req"}
    indexed = {s.get("name") for s in index.get("skills", [])}
    if not cmi_skills.intersection(indexed):
        return []  # CMI skills not installed — nothing to check

    try:
        baseline = read_json(layout.baseline)
    except Exception:
        findings.append(_fail("§6.4", "baseline parseable for CMI check", "cannot read baseline"))
        return findings

    cmi_cfg = baseline.get("cmi", {})
    if cmi_cfg.get("host"):
        findings.append(_ok("§6.4", "CMI host endpoint configured"))
    else:
        findings.append(_fail("§6.4", "CMI host endpoint configured",
                              "baseline.cmi.host not set — cmi_send will fail"))

    return findings


# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------

def run_all(layout: Layout) -> list[Finding]:
    all_findings: list[Finding] = []
    for checker in (
        check_structure,
        check_integrity,
        check_chain,
        check_skills,
        check_custom_skills,
        check_severance,
        check_cmi,
        check_session_token,
        check_drift_probes,
    ):
        all_findings.extend(checker(layout))
    return all_findings


def print_report(findings: list[Finding]) -> None:
    passed = sum(1 for f in findings if f.passed)
    failed = sum(1 for f in findings if not f.passed)
    for f in findings:
        status = "PASS" if f.passed else "FAIL"
        detail = f"  ({f.detail})" if f.detail else ""
        print(f"  [{status}] {f.section} {f.check}{detail}")
    print(f"\n  {passed} passed, {failed} failed out of {len(findings)} checks")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

