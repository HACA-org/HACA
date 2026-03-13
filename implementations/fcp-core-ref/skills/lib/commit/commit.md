# commit

Stages and commits changes in the active `workspace_focus` project.

## Parameters

- `path` (required) — path to commit, relative to the `workspace_focus` project root.
- `message` (required) — commit message.
- `remote` (optional) — if set to any non-empty value, also pushes to `origin` after committing.

## Behaviour

1. Reads `state/workspace_focus.json` to determine the active project directory.
2. Validates that `path` resolves within the workspace_focus project root.
3. Runs `git add <path>` then `git commit -m <message>` inside the project directory.
4. If `remote` is set, runs `git push origin HEAD`.

## Errors

- `workspace_focus` not set → exit 1.
- `workspace_focus` path does not exist → exit 1.
- `path` resolves outside `workspace_focus` → exit 1.
- Git command failure → exit 1 with git's error output.

## Boundary rule

This skill operates exclusively within `workspace/` projects. It never touches
entity root structural content. The Endure domain (`/endure sync`) and the
workspace domain (`commit`) never overlap (§9.5, §12.3.2).
