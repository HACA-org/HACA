# Skill: snapshot_create

Cria um snapshot compactado (tar.gz) dos arquivos vitais da entidade: `persona/`, `skills/`, `BOOT.md`, `state/integrity.json`, `state/drift-probes.jsonl`, `hooks/`.

Use antes de mutações críticas em `BOOT.md` ou skills core (obrigatório pela `persona/constraints.md`).

## Usage

```json
{
  "skill": "snapshot_create",
  "params": {
    "reason": "Antes de atualizar skill memory_store para v3"
  }
}
```

## Output

Escreve um envelope ACP `MSG` do tipo `episodic` na MIL registrando o snapshot criado.
Arquivo salvo em: `snapshots/snapshot_<timestamp>.tar.gz`
