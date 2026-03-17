# worker_skill

Instantiates an isolated sub-agent with a given persona, context, and task, returning the
result as a `SKILL_RESULT` envelope.

## Parameters

- `persona` (required) — persona text to inject into the sub-agent's system prompt.
- `context` (required) — context to provide to the sub-agent.
- `task` (required) — task description for the sub-agent.

## Status

**Deferred to Fase 2.** No executable is present in this release. Invoking this skill
returns a `SKILL_ERROR` indicating the skill is not yet executable.

## Planned behaviour (Fase 2)

1. Instantiate a sub-agent CPE instance with the given persona and context.
2. Run the sub-agent to completion on the task.
3. Return the sub-agent's output as a `SKILL_RESULT` via `io/inbox/`.
4. Sub-agent runs in isolation — it has no access to the parent entity's state.
