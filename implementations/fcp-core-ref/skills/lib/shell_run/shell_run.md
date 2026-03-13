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

- Marked `irreversible: true` — commands like `rm` or `mv` are possible.
  Logged in the Action Ledger for crash recovery.
- No command allowlist — scope is limited by CWD (workspace_focus only).
- Timeout: 30 seconds. Long-running commands will be killed.
