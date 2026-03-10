# Skill: memory_store

Persiste um fragmento de memória na MIL (Memory Interface Layer) usando o protocolo ACP via spool→inbox atômico.

## Envelope ACP gerado

- **actor**: `el`
- **type**: `MSG`
- **data**: payload JSON com `memory_type`, `tags`, `content`, `status`, `entity`

## Usage

```json
{
  "skill": "memory_store",
  "params": {
    "type":    "episodic",
    "tags":    "python,bug,fix",
    "content": "Descrição do que aconteceu (máx. 4000 bytes)",
    "status":  "success",
    "entity":  "none"
  }
}
```

## Memory Types

| type     | Uso                                              |
|----------|--------------------------------------------------|
| episodic | Eventos com contexto temporal (o que aconteceu) |
| semantic | Fatos sobre entidades (o que é verdade)          |
| index    | Resumos por tópico (para recuperação rápida)     |

## Notes

- A escrita é crash-safe: usa `memory/spool/el/<ts>.tmp` → `rename` → `memory/inbox/<ts>.msg`
- O SIL drena `memory/inbox/` para `memory/session.jsonl` a cada boot
- Limite por envelope: **4000 bytes** (FCP §4, The 4KB Rule)
