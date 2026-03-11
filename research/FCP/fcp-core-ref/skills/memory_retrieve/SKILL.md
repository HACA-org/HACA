# Skill: memory_retrieve

Busca fragmentos de memória na MIL lendo envelopes ACP de `memory/inbox/` e `memory/session.jsonl`.

## Usage

```json
{
  "skill": "memory_retrieve",
  "params": {
    "type":  "episodic",
    "query": "bug python",
    "limit": 10
  }
}
```

## Parameters

| param | type   | description                                          | default |
|-------|--------|------------------------------------------------------|---------|
| type  | string | episodic \| semantic \| index \| * (todos)          | —       |
| query | string | Substring de busca no conteúdo ou tags (case-insensitive) | —  |
| limit | int    | Número máximo de resultados                          | 10      |

## Sources (newest-first)

1. `memory/inbox/*.msg` — escritas recentes ainda não consolidadas pelo SIL
2. `memory/session.jsonl` — log principal já consolidado

## Flags

- `--inbox-only`   busca apenas em `memory/inbox/`
- `--session-only` busca apenas em `memory/session.jsonl`
