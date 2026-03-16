# skill_audit

Validate a skill's structure, format, and security before installation. Searches for the skill in this order: `workspace/stage/<name>/`, `skills/<name>/`, `skills/lib/<name>/`.

Run `skill_audit` after developing a skill and before submitting an `evolution_proposal` with `skill_install`. A passing audit does not guarantee the skill will be approved — the Operator reviews the proposal independently.

## What is validated

**Manifest (`manifest.json`)**
- All required fields present: `name`, `version`, `description`, `timeout_seconds`, `background`, `irreversible`, `class`
- Field types: `timeout_seconds` is a positive integer; `background` and `irreversible` are booleans; `permissions` is a list
- `class` is one of: `builtin`, `operator`, `custom`
- `name` matches the directory name
- `description` and `name` scanned for prompt injection patterns

**README.md** (if present)
- Scanned for prompt injection patterns

**Executable** (`run.py`, `run.sh`, or `run`) — optional; zero-code skills are valid
- File has execute permission (`+x`)
- `run.py`: syntax check via `py_compile`
- `run.py`: AST-based security analysis:
  - `eval()` / `exec()` forbidden
  - `subprocess` with `shell=True` forbidden
  - `os.system()` forbidden
  - Git module imports forbidden (`git`, `gitpython`, `pygit2`, `dulwich`)
  - Git CLI usage forbidden (e.g. `git commit`, `git push`)
  - Network module imports (`requests`, `urllib`, `httpx`, etc.) require `"network"` in `permissions`
  - Hardcoded absolute paths forbidden — use `entity_root`
  - Path traversal patterns (`../`) forbidden
  - Direct skill imports forbidden — skills must be invoked via FCP
  - `worker_skill` calls forbidden
  - Self-recursion detection

**Index** (`skills/index.json`)
- Checked only in `installed` mode — skipped for `pre_install`

The audit mode is inferred automatically from the skill's location: `workspace/stage/` → `pre_install`; `skills/` or `skills/lib/` → `installed`. No parameter needed.

## Examples

```
→ skill_audit({ "name": "fetch_rss" })
```

## Parameters

- `name` (required) — name of the skill to audit.
