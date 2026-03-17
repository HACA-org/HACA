# skill_audit

Validates a skill's manifest, executable, and index consistency. Read-only — does not modify any files.

## Parameters

- `skill` (required) — name of the skill to audit.

## Invocation paths

1. **CPE** invokes via `skill_request` to validate skills under development.
2. **SIL** invokes as a read-only Worker Skill for `SEVERANCE_PENDING` resolution (§10.8).
3. **Operator** invokes via `/skill audit <name>` (§12.3).

## Checks performed

1. Skill directory exists (in `skills/` or `skills/lib/`).
2. `manifest.json` is present and contains a valid `name` field.
3. Executable (`execute.sh` or `execute.py`) is present and executable, if any.
4. Skill name is present in `skills/index.json`.

## Output

- `OK: <name> — manifest valid, index consistent` on success (exit 0).
- `AUDIT FAILED: <name>` followed by a list of errors on failure (exit 1).
