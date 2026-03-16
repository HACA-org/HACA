# worker_skill

Instantiate a text-only sub-agent to handle isolated analysis tasks without polluting the main context window. The worker receives a task description and optional context, reasons over them, and returns text. It has no access to tools or the filesystem.

Use `worker_skill` when the task is self-contained and produces a compact result: summarizing a large document, cross-referencing multiple files whose content you pass as context, classifying or extracting structured data from text.

Do NOT use `worker_skill` when:
- The task requires reading, writing, or listing files — use `file_reader`/`file_writer` directly.
- The task is a simple sequential operation you can do in one or two tool calls.
- You want to avoid doing work — delegation is not a shortcut.

## Examples

```
→ worker_skill({ "task": "Summarize the following changelog in 3 bullet points.", "context": "<changelog text>" })
→ worker_skill({ "task": "Extract all TODO comments from this file.", "context": "<file content>" })
→ worker_skill({ "task": "Classify each item as bug, feature, or chore.", "context": "<list>" })
```

## Parameters

- `task` (required) — task description to give the worker sub-agent.
- `context` — additional context prepended to the task message (e.g. file contents).
- `persona` — system prompt for the worker. Defaults to a generic focused sub-agent.

## Notes

The worker can only reason and return text. If you ask it to write a file, it will not — you must do it yourself with `file_writer`.
