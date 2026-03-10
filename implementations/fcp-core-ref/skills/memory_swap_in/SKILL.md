# Skill: memory_swap_in

Implements **Symlink VRAM** (FCP §7): pages archived memory fragments into `memory/active_context/` via symbolic links, enabling O(1) context assembly without an external vector database.

## How It Works

1. Searches `memory/archive/` for JSONL files matching the given keywords.
2. Ranks results by keyword hit count.
3. Creates a symlink `memory/active_context/<priority>-<name>.jsonl → ../archive/…/<file>.jsonl`.
4. Phase 4 context assembly reads `active_context/*` in sorted order — higher priority prefix = loaded later and dropped first when budget is exhausted.

## Usage (via fcp-actions)

```fcp-actions
{"action": "skill_request", "skill": "memory_swap_in", "params": {"query": "project alpha architecture", "priority": 20, "max_files": 2}}
```

### Swap in a specific date range

```fcp-actions
{"action": "skill_request", "skill": "memory_swap_in", "params": {"query": "user preferences", "date_from": "2026-01-01", "date_to": "2026-01-31", "priority": 30}}
```

### Swap out (unlink from active context)

```fcp-actions
{"action": "skill_request", "skill": "memory_swap_in", "params": {"op": "out", "swap_out": "session-1234"}}
```

## Priority Convention

| Priority | Meaning                        |
|----------|--------------------------------|
| 10–19    | Critical / always keep         |
| 20–39    | High relevance for current task|
| 40–60    | Normal (default: 50)           |
| 70–89    | Low relevance, drop first      |
| 90+      | Background / rarely needed     |

## Direct bash invocation

```bash
./memory_swap_in.sh '{"query":"codebase notes","priority":20,"max_files":3}'
```

## Output

```json
{"status":"ok","query":"codebase notes","swapped_in":["/path/to/active_context/20-session-5678.jsonl"],"priority":"20"}
```
