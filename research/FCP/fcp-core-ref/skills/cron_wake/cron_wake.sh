#!/bin/bash
# skills/cron_wake/cron_wake.sh
#
# Cognitive Scheduler — checks state/agenda.jsonl for due tasks and fires CRON_WAKE.
#
# Designed to be called by system cron (e.g., every minute) or manually.
# When a scheduled task's cron expression matches the current time:
#   1. Injects a CRON_WAKE ACP envelope into memory/inbox/
#   2. Invokes sil.sh to start a full cognitive cycle
#
# Usage:
#   ./cron_wake.sh [--dry-run]
#   * * * * * /path/to/fcp-ref/skills/cron_wake/cron_wake.sh >> /var/log/fcp-ref-cron.log 2>&1

set -euo pipefail

[ -z "${FCP_REF_ROOT:-}" ] && source "$(dirname "$0")/../load_agent_root.sh"
source "$FCP_REF_ROOT/skills/lib/acp.sh"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

AGENDA="$FCP_REF_ROOT/state/agenda.jsonl"

if [ ! -f "$AGENDA" ] || [ ! -s "$AGENDA" ]; then
    echo "[cron_wake] No agenda entries. Nothing to do."
    exit 0
fi

# --- Check each SCHEDULE entry against current time ---
FIRED=$(python3 << 'PYEOF'
import json, os, sys, datetime

agenda_path = os.environ['FCP_REF_ROOT'] + '/state/agenda.jsonl'
now         = datetime.datetime.utcnow()

def cron_matches(expr, dt):
    """Simple cron matcher: supports *, n, n-m, n/step, n,m for each field."""
    fields = expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    checks = [
        (minute, dt.minute,   0, 59),
        (hour,   dt.hour,     0, 23),
        (dom,    dt.day,      1, 31),
        (month,  dt.month,    1, 12),
        (dow,    dt.weekday(), 0, 6),  # 0=Monday (Python), cron: 0=Sunday
    ]
    for field, value, lo, hi in checks:
        if field == '*':
            continue
        matched = False
        for part in field.split(','):
            if '-' in part and '/' not in part:
                a, b = part.split('-', 1)
                if int(a) <= value <= int(b):
                    matched = True
                    break
            elif '/' in part:
                base, step = part.split('/', 1)
                start = int(base) if base != '*' else lo
                if value >= start and (value - start) % int(step) == 0:
                    matched = True
                    break
            else:
                if int(part) == value:
                    matched = True
                    break
        if not matched:
            return False
    return True

fired = []
with open(agenda_path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            envelope = json.loads(line)
            if envelope.get('type') != 'SCHEDULE':
                continue
            data = json.loads(envelope.get('data', '{}'))
            cron_expr = data.get('cron', '')
            task      = data.get('task', '')
            if cron_expr and cron_matches(cron_expr, now):
                fired.append({'cron': cron_expr, 'task': task, 'ts': envelope.get('ts', '')})
        except Exception as e:
            print(f"[cron_wake] WARN: bad agenda entry: {e}", file=sys.stderr)

for item in fired:
    print(json.dumps(item))
PYEOF
)

if [ -z "$FIRED" ]; then
    echo "[cron_wake] No tasks due at $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    exit 0
fi

# --- For each fired task, inject CRON_WAKE envelope ---
while IFS= read -r task_json; do
    [ -z "$task_json" ] && continue

    local_task=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('task',''))" "$task_json")
    local_cron=$(python3 -c "import json,sys; print(json.loads(sys.argv[1]).get('cron',''))" "$task_json")

    echo "[cron_wake] Firing: cron='${local_cron}' task='${local_task}'"

    if [ "$DRY_RUN" = "false" ]; then
        WAKE_DATA=$(python3 -c "import json,sys; print(json.dumps({'cron':sys.argv[1],'task':sys.argv[2],'triggered_at':'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'}))" \
                   "$local_cron" "$local_task")
        acp_write "sil" "CRON_WAKE" "$WAKE_DATA" >/dev/null
    fi
done <<< "$FIRED"

# --- Trigger a full cognitive cycle ---
if [ "$DRY_RUN" = "false" ]; then
    echo "[cron_wake] Launching SIL cognitive cycle..."
    bash "$FCP_REF_ROOT/sil.sh" --skip-drift
else
    echo "[cron_wake] DRY RUN — SIL not invoked."
fi
