# file_reader

Read a file or list a directory within `workspace/`. All paths are relative to the workspace root. Rejects any path outside `workspace/`.

Use `"."` to list the workspace root directory.

## Examples

```
→ file_reader({ "path": "." })
→ file_reader({ "path": "src/main.py" })
→ file_reader({ "path": "docs/" })
```

## Parameters

- `path` (required) — path relative to workspace root. Use `"."` to list the root.
