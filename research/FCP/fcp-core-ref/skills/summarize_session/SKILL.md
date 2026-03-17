# Skill: summarize_session

Salva um resumo da sessão na MIL como entrada do tipo `index`. Use antes de um context flush para preservar o estado mental atual.

## Usage

```json
{
  "skill": "summarize_session",
  "params": {
    "summary":   "Implementei o SIL completo com 7 fases de boot. Skills migradas para ACP.",
    "next_step": "Fase D: drift probes com embedding backend"
  }
}
```

## Output

Escreve um envelope ACP `MSG` com `memory_type: index` e tags `session_summary,mind_flush,index`.
O timestamp é incluído automaticamente no conteúdo.
