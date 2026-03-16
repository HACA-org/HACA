# skill_audit

Validate a skill staged in `workspace/stage/<name>/` before proposing installation. Checks that the manifest is well-formed, required fields are present, and the executable (if any) exists and is syntactically valid.

Run `skill_audit` after developing a skill and before submitting an `evolution_proposal` with `skill_install`. A passing audit does not guarantee the skill will be approved — the Operator reviews the proposal independently.

## Examples

```
→ skill_audit({ "name": "fetch_rss" })
```

## Parameters

- `name` (required) — name of the skill to audit. Must match a directory in `workspace/stage/<name>/`.
