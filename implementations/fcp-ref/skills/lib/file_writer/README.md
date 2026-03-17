# file_writer

Write a file within `workspace/`. Creates parent directories if needed. All paths are relative to the workspace root. Rejects any path outside `workspace/`.

Always writes the full file content — there is no append or patch mode. To update a file, read it first with `file_reader`, modify the content, then write it back.

## Examples

```
→ file_writer({ "path": "notes.md", "content": "# Notes\n\nHello." })
→ file_writer({ "path": "src/utils.py", "content": "..." })
```

## Parameters

- `path` (required) — path relative to workspace root.
- `content` (required) — full file content to write.
