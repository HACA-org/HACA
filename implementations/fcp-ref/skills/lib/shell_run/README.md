# shell_run

Execute an allowed shell command within `workspace_focus`. Commands run with `workspace_focus` as the working directory.

Permitted commands: `ls`, `cat`, `pwd`, `find`, `grep`. Any other command is rejected. Direct git access is not permitted — use `commit` instead.

## Examples

```
→ shell_run({ "command": "ls -la" })
→ shell_run({ "command": "find . -name '*.py'" })
→ shell_run({ "command": "grep -r 'TODO' src/" })
```

## Parameters

- `command` (required) — shell command to execute. Must begin with a permitted command.

## Notes

Requires `workspace_focus` to be set. Returns an error if it is not defined.
