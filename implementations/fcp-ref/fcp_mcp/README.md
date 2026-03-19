# fcp-mcp — FCP MCP Server

Bridges any MCP-capable IDE or CLI to an active FCP pairing session.

When FCP runs with `backend = pairing`, it writes prompts to the filesystem and waits for a completion. This server exposes those prompts as MCP tools, so any connected agent (Claude Code, Cursor, Zed, or any MCP client) can pick them up, process them, and return the response back to FCP — without API keys, without extra processes, and without manual intervention.

---

## How it works

```
┌─────────────────────┐        ~/.fcp/pairing/        ┌──────────────────────┐
│   FCP (entity)      │  ── <session>.request.json ──▶ │   fcp-mcp server     │
│   backend=pairing   │  ◀─ <session>.response.json ── │   (MCP tools)        │
└──────────┬──────────┘                                └──────────┬───────────┘
           │ on_prompt_pending hook                               │ MCP protocol
           │                                           ┌──────────▼───────────┐
           └──────────────────────────────────────────▶│  IDE / CLI agent     │
                (wakes IDE when prompt ready)          │  (Claude Code, etc.) │
                                                       └──────────────────────┘
```

### Workflow

1. FCP writes a prompt to `~/.fcp/pairing/<session-id>.request.json` and blocks.
2. FCP fires `on_prompt_pending` hook — notifies the IDE/CLI that a prompt is ready.
3. The connected agent (woken by hook or polling) calls `fcp_poll` — the server reads and removes the request file, returning the prompt.
4. The agent processes the prompt and calls `fcp_respond` with the completion.
5. The server writes `~/.fcp/pairing/<session-id>.response.json`.
6. FCP detects the response file, reads it, and continues the session.

### Hook-based notification (default)

When FCP writes a prompt, it automatically dispatches the `on_prompt_pending` hook. This allows the IDE to wake up immediately without continuous polling.

**Hook location:** `.fcp-entity/hooks/on_prompt_pending/`

Example hook (Claude Code):
```bash
#!/bin/bash
# .fcp-entity/hooks/on_prompt_pending/notify_claude_code
# Creates a marker file that Claude Code monitors
SESSION_ID=$(echo "$FCP_EVENT_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
mkdir -p "${FCP_ENTITY_ROOT}/.fcp-entity/notifications/mcp"
echo "{...}" > "${FCP_ENTITY_ROOT}/.fcp-entity/notifications/mcp/${SESSION_ID}.pending"
```

The server is a **persistent, independent process** — it stays alive across multiple FCP sessions. No restart needed between `fcp` invocations.

---

## Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (recommended) — or `pip`

---

## Installation

### With uvx (recommended — no manual install)

No installation needed. Configure your IDE/CLI to run it directly via `uvx`:

```json
{
  "mcpServers": {
    "fcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/HACA-org/HACA#subdirectory=implementations/fcp-ref/fcp_mcp",
        "fcp-mcp"
      ]
    }
  }
}
```

`uvx` downloads, installs dependencies in an isolated environment, and runs the server — automatically.

### With pip (manual)

```bash
pip install git+https://github.com/HACA-org/HACA#subdirectory=implementations/fcp-ref/fcp_mcp
fcp-mcp
```

### From local source

```bash
cd implementations/fcp-ref/fcp_mcp
pip install -e .
fcp-mcp
```

---

## IDE / CLI Configuration

### Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "fcp": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/HACA-org/HACA#subdirectory=implementations/fcp-ref/fcp_mcp",
        "fcp-mcp"
      ]
    }
  }
}
```

### Cursor

Open **Settings → MCP** and add:

```json
{
  "fcp": {
    "command": "uvx",
    "args": [
      "--from",
      "git+https://github.com/HACA-org/HACA#subdirectory=implementations/fcp-ref/fcp_mcp",
      "fcp-mcp"
    ]
  }
}
```

### Zed

Add to `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "fcp": {
      "command": {
        "path": "uvx",
        "args": [
          "--from",
          "git+https://github.com/HACA-org/HACA#subdirectory=implementations/fcp-ref/fcp_mcp",
          "fcp-mcp"
        ]
      }
    }
  }
}
```

---

## Usage guide

### 1. Start FCP with pairing backend

```bash
fcp init        # select backend: pairing, model: external
fcp             # start a session — banner appears:
```

```
────────────────────────────────────────────────────
  PAIRING MODE ACTIVE
  Session  : a3f1c9b2
  Key      : HACA-GJP3-A
  MCP Dir  : /home/user/.fcp/pairing
  Connect the FCP MCP Server to your IDE/CLI.
────────────────────────────────────────────────────
```

### 2. Connect the MCP server

Your IDE/CLI connects automatically on startup if configured. To verify, ask the agent:

> "List active FCP sessions"

Expected response:

```json
{
  "sessions": [
    {
      "session_id": "a3f1c9b2",
      "key": "HACA-GJP3-A",
      "started_at": "2026-03-19T13:45:00Z",
      "status": "active",
      "pending": false
    }
  ]
}
```

### 3. The agent loop

Once connected, the agent operates in a cycle:

**With hook-based notification (recommended):**
```
[hook fires on_prompt_pending]
    ↓
[IDE wakes and calls fcp_poll]
    ↓
fcp_poll      →  retrieve pending prompt
    ↓
fcp_respond   →  deliver completion back to FCP
    ↓
[repeat when next prompt ready]
```

**With continuous polling (fallback):**
```
fcp_sessions  →  find active session
    ↓
fcp_poll      →  check for pending prompt  (repeat every N seconds)
    ↓
fcp_respond   →  deliver completion back to FCP
```

**Hook notification is preferred** because it wakes the IDE immediately, without wasting CPU on polling. The entity can customize hook behavior in `.fcp-entity/hooks/on_prompt_pending/`.

---

## MCP Tools reference

### `fcp_sessions`

List all active pairing sessions.

**Parameters:** none

**Returns:**
```json
{
  "sessions": [
    {
      "session_id": "a3f1c9b2",
      "key": "HACA-GJP3-A",
      "model": "external",
      "started_at": "2026-03-19T13:45:00Z",
      "status": "active",
      "pending": true
    }
  ]
}
```

`pending: true` means a prompt is waiting to be picked up.

---

### `fcp_poll`

Retrieve and consume the pending prompt for a session.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `session_id` | string | Session ID from `fcp_sessions` |

**Returns (prompt available):**
```json
{
  "pending": true,
  "session_id": "a3f1c9b2",
  "system": "...",
  "messages": [...],
  "tools": [...]
}
```

**Returns (no prompt yet):**
```json
{ "pending": false }
```

The request file is deleted after a successful poll — calling `fcp_poll` twice does not return the same prompt twice.

---

### `fcp_respond`

Deliver a completion back to the waiting FCP session.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `session_id` | string | yes | Session ID from `fcp_sessions` |
| `text` | string | yes | Narrative response (may be empty if tool calls present) |
| `tool_use_calls` | array | no | Tool calls: `[{"id": "...", "tool": "...", "input": {...}}]` |
| `stop_reason` | string | no | `"end_turn"` \| `"tool_use"` \| `"max_tokens"` (default: `"end_turn"`) |
| `input_tokens` | int | no | Token count, informational only |
| `output_tokens` | int | no | Token count, informational only |

**Returns:**
```json
{ "status": "delivered", "session_id": "a3f1c9b2" }
```

FCP unblocks within 250ms of the response file being written.

---

## Filesystem layout

```
~/.fcp/pairing/
  <session-id>.meta.json      — session metadata (id, key, status, started_at)
  <session-id>.request.json   — prompt written by FCP; deleted after fcp_poll
  <session-id>.response.json  — completion written by fcp_respond; deleted after FCP reads
```

Files are cleaned up automatically when the FCP session ends. Orphaned meta files (from crashed sessions) can be removed manually or via a cron job.

---

## Hook customization

The `.fcp-entity/hooks/on_prompt_pending/` directory can contain multiple notification scripts, one per IDE/CLI:

```
hooks/on_prompt_pending/
  notify_claude_code    — writes marker file to .fcp-entity/notifications/mcp/
  notify_cursor         — calls HTTP webhook
  notify_antigravity    — sends MCP callback
```

Each script receives:
- `FCP_EVENT` = `"on_prompt_pending"`
- `FCP_ENTITY_ROOT` = entity root path
- `FCP_EVENT_DATA` = JSON with `session_id` and `request_file`

Example: create a custom script that immediately calls `fcp_poll`:
```bash
#!/bin/bash
# .fcp-entity/hooks/on_prompt_pending/notify_my_ide
SESSION_ID=$(echo "$FCP_EVENT_DATA" | jq -r '.session_id')
# Call your IDE's API or trigger fcp_poll via subprocess
curl -X POST http://localhost:8888/notify?session=$SESSION_ID &
```

---

## Troubleshooting

**`fcp_sessions` returns empty**
FCP is not running with `backend = pairing`. Run `fcp` and check the banner appears.

**`fcp_poll` always returns `{"pending": false}`**
The operator has not sent a message in the FCP session yet. Send a message in FCP first.

**FCP times out after 300s**
The agent did not call `fcp_respond` within the timeout. Check that the MCP server is running and the agent is actively polling.

**Stale `.meta.json` files after a crash**
```bash
rm ~/.fcp/pairing/*.meta.json
rm ~/.fcp/pairing/*.request.json
rm ~/.fcp/pairing/*.response.json
```
