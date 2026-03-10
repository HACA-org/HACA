# Skill: cron_wake

Cognitive Scheduler — verifica `state/agenda.jsonl` em busca de tarefas cujo cron expression casa com o horário atual e injeta `CRON_WAKE` na MIL para acordar o CPE.

## Operação autônoma

Este skill é projetado para ser chamado pelo cron do sistema a cada minuto:

```cron
* * * * * /path/to/fcp-ref/skills/cron_wake/cron_wake.sh >> /var/log/fcp-ref.log 2>&1
```

## Invocação manual

```bash
./cron_wake.sh           # Verifica agenda e dispara SIL se houver tarefas
./cron_wake.sh --dry-run # Verifica sem disparar
```

## Cron expression format

```
┌──────── minute (0-59)
│  ┌───── hour (0-23)
│  │  ┌── day-of-month (1-31)
│  │  │  ┌─ month (1-12)
│  │  │  │  ┌ day-of-week (0-6, 0=Sunday)
│  │  │  │  │
*  *  *  *  *
```

Suporta: `*`, valores simples, ranges (`1-5`), listas (`1,3,5`), steps (`*/15`).

## Flow

```
state/agenda.jsonl (SCHEDULE envelopes)
    → parse cron expression
    → match against current UTC time
    → acp_write "sil" "CRON_WAKE" {cron, task, triggered_at}
    → memory/inbox/<ts>.msg
    → bash sil.sh --skip-drift   (cognitive cycle)
```

## Agenda entries

O CPE adiciona entradas via action `agenda_add` no bloco `fcp-actions`:

```fcp-actions
{"action": "agenda_add", "cron": "0 9 * * 1-5", "task": "Summarize yesterday and plan the day"}
```
