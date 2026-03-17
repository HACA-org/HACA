# skill_create

Scaffold a new skill in `workspace/stage/<name>/` for installation via `evolution_proposal`. Creates a `manifest.json` template and a `README.md` stub. A `run.*` executable is optional — skills without one are documentation-only or delegate logic to the README.

Use `--base <name>` to clone an existing skill as a starting point instead of generating a blank template.

## Examples

```
→ skill_create({ "name": "fetch_rss" })
→ skill_create({ "name": "fetch_rss", "base": "web_fetch" })
```

## Parameters

- `name` (required) — name of the new skill. Must not already exist in `workspace/stage/`.
- `base` — name of an existing installed skill to clone as a starting point.

## Skill install workflow

`skill_create` → develop in `workspace/stage/<name>/` → `skill_audit` → `evolution_proposal` with `skill_install` → Operator approves → skill available at next boot.
