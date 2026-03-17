# file_writer

Writes content to a file within `workspace/`.

## Parameters

- `path` (required) — path to the file, relative to `workspace/`. Must resolve inside `workspace/`.
- `content` (required) — content to write. Overwrites the file if it exists; creates it otherwise.

## Behaviour

- Rejects any path that resolves outside `workspace/` (path traversal via `..` or absolute paths).
- Parent directories are created automatically.
- No file size limit beyond host disk capacity.

## Errors

- Path resolves outside `workspace/` → exit 1 with rejection message.
