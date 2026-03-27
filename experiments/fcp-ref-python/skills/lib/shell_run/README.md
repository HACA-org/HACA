# shell_run

Execute an allowed shell command within `workspace_focus`. Commands run with `workspace_focus` as the working directory.

Permitted commands are declared in the skill manifest allowlist. Any other command is rejected. `git` commands are permitted within `workspace_focus` — the system automatically blocks operations that would affect the entity's internal repository.

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
