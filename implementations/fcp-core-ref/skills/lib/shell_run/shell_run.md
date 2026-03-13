# shell_run

Execute a shell command in the active `workspace_focus` project directory.

## Parameters

- `command` (required) — bash command string to run.

## Behaviour

- Runs with CWD set to `workspace/<focus_path>/`.
- Requires `workspace_focus` to be set; returns an error otherwise.
- stdout and stderr are merged into a single output stream.
- Output is truncated to 16 KB; a notice is appended when truncation occurs.
- Exit code propagates: non-zero exits report as skill error.

## Examples

```fcp-exec
{"type": "skill_request", "skill": "shell_run",
 "params": {"command": "grep -rn 'TODO' src/"}}
```

```fcp-exec
{"type": "skill_request", "skill": "shell_run",
 "params": {"command": "ls -la"}}
```

```fcp-exec
{"type": "skill_request", "skill": "shell_run",
 "params": {"command": "git status"}}
```

## Notes

- Only the base command (first token) is validated against the `allowlist` in
  `manifest.json`. Flags and arguments are passed through unchecked.
- To expand the allowlist, submit an `evolution_proposal` targeting
  `skills/lib/shell_run/manifest.json` with an updated `"allowlist"` array.
- Marked `irreversible: true` — logged in the Action Ledger for crash recovery.
- Timeout: 30 seconds. Long-running commands will be killed.
