# file_reader

Reads a file from within `workspace/` and delivers its contents as a `SKILL_RESULT`.

## Parameters

- `path` (required) — path to the file, relative to `workspace/`. Must resolve inside `workspace/`.

## Behaviour

- Rejects any path that resolves outside `workspace/` (path traversal via `..` or absolute paths).
- Returns the raw file content as stdout; the FCP framework delivers it as a chunked `SKILL_RESULT`.
- No file size limit — the practical limit is the CPE's available context budget.

## Errors

- Path does not exist → exit 1 with descriptive message.
- Path resolves outside `workspace/` → exit 1 with rejection message.
