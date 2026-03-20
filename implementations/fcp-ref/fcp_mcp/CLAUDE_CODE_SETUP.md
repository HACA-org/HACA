# Claude Code + FCP MCP Integration Setup

## Quick Start

This guide helps you set up Claude Code to automatically trigger `fcp_poll` when FCP has a pending prompt via MCP pairing.

### 1. Configure MCP Server in Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "fcp": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/home/estupendo/code/HACA/implementations/fcp-ref/fcp_mcp",
        "fcp-mcp"
      ]
    }
  }
}
```

Then restart Claude Code for changes to take effect.

### 2. Start the FCP Listener

In Claude Code terminal, run this command to monitor for pending prompts:

```bash
/loop 500ms bash -c 'ls -t ~/.fcp-entity/notifications/mcp/*.pending 2>/dev/null | head -1 | xargs -r bash -c "session_id=\${1%.pending}; session_id=\${session_id##*/}; fcp_poll \$session_id; rm \$1" _ {}'
```

**What this does:**
- Checks every 500ms for `.pending` files in `~/.fcp-entity/notifications/mcp/`
- Extracts session ID from filename
- Calls `fcp_poll <session_id>` automatically
- Removes the `.pending` file after polling

### 3. Test the Integration

In one Claude Code terminal, start an FCP session with pairing backend:

```bash
cd /path/to/fcp-entity
fcp
```

You should see:
```
────────────────────────────────────────────────────
  PAIRING MODE ACTIVE
  Session  : a3f1c9b2
  Key      : HACA-GJP3-A
  MCP Dir  : /home/estupendo/.fcp/pairing
  Connect the FCP MCP Server to your IDE/CLI.
────────────────────────────────────────────────────
```

In the same Claude Code instance (where you have the `/loop` running), send a message to FCP:

```
> Hello, I'm connected via pairing!
```

**Expected flow:**
1. FCP processes your message
2. When FCP calls `PairingAdapter.invoke()` to get the next prompt
3. Hook `on_prompt_pending` fires
4. Creates `.pending` marker file in `~/.fcp-entity/notifications/mcp/<session_id>.pending`
5. `/loop` detects the file
6. `/loop` calls `fcp_poll <session_id>` automatically
7. You get the prompt in Claude Code without manual intervention

### 4. Alternative: Named Pipe Setup (More Efficient)

If you want to avoid polling directory, use named pipes:

```bash
# Create the named pipe (one-time setup in Claude Code terminal)
mkdir -p ~/.fcp-entity/signals
mkfifo ~/.fcp-entity/signals/mcp_wake 2>/dev/null || true

# Run listener
/loop 100ms bash -c 'read -t 0.1 session_id < ~/.fcp-entity/signals/mcp_wake 2>/dev/null && [ -n "$session_id" ] && fcp_poll "$session_id"'
```

**How it works:**
- Hook writes session_id to the named pipe
- `/loop` listener reads from the pipe
- Wakes up immediately (no polling needed)
- More efficient than directory polling

---

## Troubleshooting

### `/loop` not running?

Check if `/loop` is available as a skill in Claude Code:

```
/help
```

If not available, use polling fallback:

```bash
while true; do
  ls -t ~/.fcp-entity/notifications/mcp/*.pending 2>/dev/null | head -1 | xargs -r bash -c 'fcp_poll "${1%.pending}" && rm "$1"' _
  sleep 0.5
done
```

### Not receiving prompts?

1. Check that MCP server is connected:
   ```
   fcp_sessions
   ```
   Should return active sessions.

2. Check hook is firing:
   ```
   tail -f ~/.fcp-entity/.fcp-entity/logs/mcp_notifications.log
   ```

3. Check marker files are being created:
   ```
   ls -la ~/.fcp-entity/notifications/mcp/
   ```

4. Check named pipe (if using):
   ```
   ls -la ~/.fcp-entity/signals/mcp_wake
   ```

### FCP timeout (300s)?

If FCP times out waiting for response, the listener process crashed. Restart it:

```
/loop 500ms bash -c 'ls -t ~/.fcp-entity/notifications/mcp/*.pending 2>/dev/null | head -1 | xargs -r bash -c "fcp_poll \${1%.pending}" _'
```

---

## Architecture

```
FCP Session (pairing backend)
    ↓
writes ~/.fcp/pairing/<session-id>.request.json
    ↓
Hook on_prompt_pending fires
    ↓
Creates ~/.fcp-entity/notifications/mcp/<session_id>.pending
    ↓
/loop listener detects file
    ↓
Calls: fcp_poll <session_id>
    ↓
fcp_poll retrieves prompt from MCP server
    ↓
Claude Code processes prompt
    ↓
Claude Code calls: fcp_respond with completion
    ↓
FCP continues session
```

---

## Next Steps

- Test with a simple entity (e.g., `/home/estupendo/code/bots/core-test`)
- Monitor logs: `tail -f ~/.fcp-entity/.fcp-entity/logs/mcp_notifications.log`
- If reliable, make `/loop` permanent in Claude Code settings
