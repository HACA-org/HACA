# file_reader

Read a file or list a directory within `workspace/`. All paths are relative to the workspace root. Rejects any path outside `workspace/`.

Use `"."` to list the workspace root directory.

## Examples

```
→ file_reader({ "path": "." })
→ file_reader({ "path": "src/main.py" })
→ file_reader({ "path": "src/main.py", "offset": 1, "limit": 200 })
→ file_reader({ "path": "src/main.py", "offset": 201, "limit": 200 })
```

## Parameters

- `path` (required) — path relative to workspace root. Use `"."` to list the root.
- `offset` — first line to read, 1-indexed. Defaults to 1.
- `limit` — maximum number of lines to return. Defaults to entire file.

The response includes `total_lines` so you can paginate if needed.
