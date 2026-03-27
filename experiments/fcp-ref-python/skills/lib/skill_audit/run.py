#!/usr/bin/env python3
"""skill_audit — validate a skill before installation."""

from __future__ import annotations
import ast
import json
import os
import py_compile
import re
import shutil
import sys
import tempfile
from pathlib import Path

REQUIRED_MANIFEST_FIELDS = ["name", "version", "description", "timeout_seconds",
                             "background", "irreversible", "class", "execution",
                             "dependencies"]

VALID_EXECUTION_TYPES = {"script", "text"}

VALID_CLASSES = {"builtin", "operator", "custom"}

NETWORK_MODULES = {"requests", "urllib", "urllib2", "urllib3", "httpx", "aiohttp",
                   "socket", "http", "ftplib", "smtplib", "imaplib"}

PROMPT_INJECT_PATTERNS = [
    r"ignore\s+(previous|prior|above|all)\s+(instructions?|prompts?|context)",
    r"you\s+are\s+now",
    r"disregard\s+(all|previous|prior|your)",
    r"forget\s+(all|everything|your|previous)",
    r"new\s+persona",
    r"act\s+as\s+(if\s+you\s+are|a\s+)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"override\s+(your\s+)?(instructions?|constraints?|rules?)",
    r"system\s*:\s*you",
    r"\[system\]",
    r"</?(system|instruction|prompt)>",
]

_INJECT_RE = re.compile("|".join(PROMPT_INJECT_PATTERNS), re.IGNORECASE)


# ---------------------------------------------------------------------------
# manifest validation
# ---------------------------------------------------------------------------

def _check_manifest(manifest: dict, name: str, issues: list[str]) -> None:
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in manifest:
            issues.append(f"missing manifest field: {field}")

    if manifest.get("name") != name:
        issues.append(f"manifest name mismatch: {manifest.get('name')!r} != {name!r}")

    ts = manifest.get("timeout_seconds")
    if ts is not None and (not isinstance(ts, int) or ts <= 0):
        issues.append("timeout_seconds must be a positive integer")

    for bool_field in ("background", "irreversible"):
        val = manifest.get(bool_field)
        if val is not None and not isinstance(val, bool):
            issues.append(f"{bool_field} must be a boolean")

    perms = manifest.get("permissions")
    if perms is not None and not isinstance(perms, list):
        issues.append("permissions must be a list")

    cls = manifest.get("class")
    if cls is not None and cls not in VALID_CLASSES:
        issues.append(f"invalid class {cls!r} — must be one of {sorted(VALID_CLASSES)}")

    execution = manifest.get("execution")
    if execution is not None and execution not in VALID_EXECUTION_TYPES:
        issues.append(f"invalid execution {execution!r} — must be one of {sorted(VALID_EXECUTION_TYPES)}")

    deps = manifest.get("dependencies")
    if deps is not None:
        if not isinstance(deps, list):
            issues.append("dependencies must be a list")
        else:
            for dep in deps:
                if not isinstance(dep, str):
                    issues.append(f"dependency entry must be a string, got {dep!r}")
                elif shutil.which(dep) is None:
                    issues.append(f"dependency not found on host: {dep!r}")


# ---------------------------------------------------------------------------
# text / prompt injection checks
# ---------------------------------------------------------------------------

def _check_text(label: str, text: str, issues: list[str]) -> None:
    if _INJECT_RE.search(text):
        issues.append(f"possible prompt injection pattern detected in {label}")


# ---------------------------------------------------------------------------
# executable security analysis (AST-based for .py)
# ---------------------------------------------------------------------------

def _check_executable_py(path: Path, name: str, declared_permissions: list,
                          issues: list[str]) -> None:
    # syntax check
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(path.read_bytes())
    try:
        py_compile.compile(tmp_path, doraise=True)
    except py_compile.PyCompileError as exc:
        issues.append(f"syntax error in {path.name}: {exc}")
        return
    finally:
        os.unlink(tmp_path)

    # permissions / execute bit
    if not os.access(path, os.X_OK):
        issues.append(f"{path.name} is not executable (chmod +x required)")

    source = path.read_text(encoding="utf-8", errors="replace")

    # prompt injection in source comments/strings
    _check_text(path.name, source, issues)

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return  # already caught above

    for node in ast.walk(tree):
        # eval / exec
        if isinstance(node, ast.Call):
            func = node.func
            func_name = (func.id if isinstance(func, ast.Name) else
                         func.attr if isinstance(func, ast.Attribute) else None)
            if func_name in ("eval", "exec"):
                issues.append(f"forbidden: use of {func_name}() in {path.name}")

            # subprocess with shell=True
            if isinstance(func, ast.Attribute) and func.attr in ("run", "call", "Popen",
                                                                   "check_output",
                                                                   "check_call"):
                for kw in node.keywords:
                    kw_val = kw.value
                    if kw.arg == "shell" and isinstance(kw_val, ast.Constant) and kw_val.value:
                        issues.append(f"forbidden: subprocess with shell=True in {path.name}")

            # os.system
            func_obj = func.value if isinstance(func, ast.Attribute) else None
            if (isinstance(func, ast.Attribute) and func.attr == "system"
                    and isinstance(func_obj, ast.Name) and func_obj.id == "os"):
                issues.append(f"forbidden: os.system() in {path.name}")

            # worker_skill call
            if func_name == "worker_skill":
                issues.append(f"forbidden: recursive worker_skill call in {path.name}")

        # import checks
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = ([alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""])
            for mod in mods:
                base = mod.split(".")[0]

                # git access
                if base in ("git", "gitpython", "pygit2", "dulwich"):
                    issues.append(f"forbidden: git module import ({mod}) in {path.name}")

                # network without permission
                if base in NETWORK_MODULES and "network" not in declared_permissions:
                    issues.append(
                        f"network module {mod!r} imported but 'network' not in permissions")

        # path traversal / absolute paths in string literals
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value
            if val.startswith("/") and len(val) > 1:
                issues.append(f"hardcoded absolute path {val!r} in {path.name} — use entity_root")
            if ".." in val and ("/" in val or "\\" in val):
                issues.append(f"path traversal pattern {val!r} in {path.name}")

    # git CLI usage in source
    git_cli_re = re.compile(r'\bgit\s+\w', re.IGNORECASE)
    if git_cli_re.search(source):
        issues.append(f"forbidden: git CLI usage detected in {path.name}")

    # skill-to-skill invocation heuristic
    # skills communicate via FCP, not by importing each other
    skill_import_re = re.compile(r'\bfrom\s+skills\b|\bimport\s+skills\b')
    if skill_import_re.search(source):
        issues.append(f"forbidden: direct skill import in {path.name} — skills must be invoked via FCP")

    # self-recursion (skill calling itself by name)
    self_call_re = re.compile(rf'\b{re.escape(name)}\s*\(')
    if self_call_re.search(source):
        issues.append(f"possible self-recursion: {name}() call detected in {path.name}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    req = json.loads(sys.stdin.read())
    params = req.get("params", {})
    entity_root = Path(req.get("entity_root", "."))

    name = str(params.get("name", "")).strip()
    if not name:
        print(json.dumps({"error": "missing required param: name"}))
        sys.exit(1)

    issues: list[str] = []

    # locate manifest — stage takes priority, then installed, then builtin
    stage_path = Path("/tmp") / "fcp-stage" / entity_root.name / name / "manifest.json"
    installed_path = entity_root / "skills" / name / "manifest.json"
    lib_path = entity_root / "skills" / "lib" / name / "manifest.json"
    candidates = [stage_path, installed_path, lib_path]

    manifest_path = next((p for p in candidates if p.exists()), candidates[0])
    in_stage = manifest_path == stage_path

    if not manifest_path.exists():
        issues.append(f"manifest not found in /tmp/fcp-stage/<entity_id>/{name}/, skills/{name}/, or skills/lib/{name}/")
        print(json.dumps({"skill": name, "valid": False, "issues": issues}))
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(f"manifest parse error: {exc}")
        print(json.dumps({"skill": name, "valid": False, "issues": issues}))
        return

    _check_manifest(manifest, name, issues)

    # check description and name for prompt injection
    _check_text("manifest.description", manifest.get("description", ""), issues)
    _check_text("manifest.name", manifest.get("name", ""), issues)

    declared_permissions = manifest.get("permissions") or []
    skill_dir = manifest_path.parent

    # README check
    readme = skill_dir / "README.md"
    if readme.exists():
        _check_text("README.md", readme.read_text(encoding="utf-8", errors="replace"), issues)

    execution_type = manifest.get("execution", "script")
    run_py = skill_dir / "run.py"
    run_sh = skill_dir / "run.sh"
    run_bin = skill_dir / "run"
    has_executable = run_py.exists() or run_sh.exists() or run_bin.exists()

    if execution_type == "text":
        # text-only skill: must have instructions file, must NOT have executable
        instructions_file = manifest.get("instructions", "README.md")
        instructions_path = skill_dir / instructions_file
        if not instructions_path.exists():
            issues.append(f"text-only skill missing instructions file: {instructions_file!r}")
        else:
            _check_text(instructions_file, instructions_path.read_text(encoding="utf-8", errors="replace"), issues)
        if has_executable:
            issues.append("text-only skill should not have an executable (run.py/run.sh/run)")
    else:
        # script skill: must have executable
        if run_py.exists():
            _check_executable_py(run_py, name, declared_permissions, issues)
        elif run_sh.exists():
            if not os.access(run_sh, os.X_OK):
                issues.append("run.sh is not executable (chmod +x required)")
            src = run_sh.read_text(encoding="utf-8", errors="replace")
            _check_text("run.sh", src, issues)
            if re.search(r'\bgit\s+\w', src, re.IGNORECASE):
                issues.append("forbidden: git CLI usage detected in run.sh")
        elif run_bin.exists():
            if not os.access(run_bin, os.X_OK):
                issues.append("run is not executable (chmod +x required)")
        else:
            issues.append("script skill missing executable (run.py, run.sh, or run)")

    # index check — only for installed skills (not stage)
    if not in_stage:
        index_path = entity_root / "skills" / "index.json"
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
                names = [s.get("name") for s in index.get("skills", [])]
                if name not in names:
                    issues.append("skill absent from skills/index.json")
            except Exception as exc:
                issues.append(f"index parse error: {exc}")
        else:
            issues.append("skills/index.json not found")

    print(json.dumps({
        "skill": name,
        "valid": len(issues) == 0,
        "issues": issues,
    }))


main()
