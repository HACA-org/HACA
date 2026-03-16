# commit

Stage and commit a path within `workspace_focus`. This is the only version-control interface available to the CPE — direct git access via `shell_run` is rejected. Optionally pushes to origin after committing.

## Examples

```
→ commit({ "path": "notes.md", "message": "add notes" })
→ commit({ "path": "src/", "message": "refactor parser", "remote": true })
```

## Parameters

- `path` (required) — path within `workspace_focus` to stage and commit.
- `message` — commit message. Defaults to a generic message if omitted.
- `remote` — if `true`, push to origin after committing.

## Notes

Requires `workspace_focus` to be set. Returns an error if it is not defined or if the path is outside `workspace_focus`.
