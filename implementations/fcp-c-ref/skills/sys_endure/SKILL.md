# Skill: sys_endure

**Self-Evolution via Git** (FCP §12): enables the CPE to propose deliberate changes to its own persona files, validates the proposal against drift probes, then commits the change to version control and updates `state/integrity.json`.

## Protocol

1. CPE proposes a change to a `persona/` file via `skill_request`.
2. `sys_endure` writes the proposed content to a `.proposed` temp file.
3. Drift probes run against the proposed identity (using expected_text scoring).
4. **If probes PASS**: the file is overwritten, `integrity.json` hashes are recomputed, and a git commit is made.
5. **If probes FAIL**: temp file is discarded, a `TRAP` envelope is written, no state changes occur.

## Security Constraints

- Only files under `persona/` can be modified (path traversal is rejected).
- Cannot create new persona files — only modify existing ones.
- drift probes must pass before any state change is written.
- All evolution is recorded in git history (`git log`).

## Usage (via fcp-actions)

```fcp-actions
{"action": "skill_request", "skill": "sys_endure", "params": {
    "file": "persona/values.md",
    "content": "# Values\n\nTransparency, persistence, minimal footprint, and human oversight.",
    "commit_msg": "sys_endure: clarify values — add human oversight principle"
}}
```

### Dry-run validation (no commit)

```fcp-actions
{"action": "skill_request", "skill": "sys_endure", "params": {
    "file": "persona/identity.md",
    "content": "...",
    "dry_run": true
}}
```

## Output (success)

```json
{"status": "ok", "file": "persona/values.md", "commit": "a1b2c3d4...", "drift": "PASS"}
```

## Output (drift rejection)

```json
{"status": "rejected", "reason": "drift_fail", "file": "persona/values.md"}
```
