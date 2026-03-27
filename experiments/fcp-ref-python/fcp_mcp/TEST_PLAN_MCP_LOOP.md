# Test Plan: MCP + /loop Integration

## Status: ✅ READY TO TEST

All infrastructure is in place. Time to test the complete end-to-end flow.

---

## What Was Built

1. **Hook:** `hooks/on_prompt_pending/notify_claude_code`
   - Creates marker files in `.fcp-entity/notifications/mcp/<session_id>.pending`
   - Creates named pipe `.fcp-entity/signals/mcp_wake`
   - Signals Claude Code listener when prompt pending

2. **Integration Test:** `test_mcp_loop_integration.sh`
   - ✅ Marker file creation: **PASS**
   - ✅ Named pipe communication: **PASS**
   - ✅ Listener reads from pipe: **PASS**
   - ✅ Fallback polling works: **PASS**

3. **Setup Guide:** `CLAUDE_CODE_SETUP.md`
   - Complete instructions for Claude Code configuration
   - Two listener patterns (polling and named pipe)
   - Troubleshooting guide

---

## Test Procedure

### Phase 1: Setup (One-time)

1. **Ensure fcp_mcp is configured in Claude Code:**
   ```json
   {
     "mcpServers": {
       "fcp": {
         "command": "uv",
         "args": ["run", "--project", "/home/estupendo/code/HACA/implementations/fcp-ref/fcp_mcp", "fcp-mcp"]
       }
     }
   }
   ```
   - Edit `~/.claude/settings.json`
   - Restart Claude Code

2. **Verify MCP server is running:**
   ```
   fcp_sessions
   ```
   Should return empty list (no active sessions yet).

### Phase 2: Start Listener in Claude Code

Choose one pattern:

**Option A: Named Pipe (Recommended)**
```bash
mkdir -p ~/.fcp-entity/signals
mkfifo ~/.fcp-entity/signals/mcp_wake 2>/dev/null || true
/loop 100ms bash -c 'read -t 0.1 sid < ~/.fcp-entity/signals/mcp_wake 2>/dev/null && [ -n "$sid" ] && echo "[LISTENER] Polling session $sid" && fcp_poll "$sid"'
```

**Option B: Directory Polling (Simpler)**
```bash
/loop 500ms bash -c 'ls -t ~/.fcp-entity/notifications/mcp/*.pending 2>/dev/null | head -1 | xargs -r bash -c "sid=\${1%.pending}; sid=\${sid##*/}; echo \"[LISTENER] Polling \$sid\"; fcp_poll \$sid; rm \$1" _'
```

### Phase 3: Start FCP Session with Pairing

In Claude Code terminal 2 (or separate window):
```bash
cd /home/estupendo/code/bots/core-test
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

### Phase 4: Send a Message to FCP

In FCP session, send a message. You should see:

**FCP terminal:**
```
[FCP] Operator: Hello! Test message
[FCP] Waiting for CPE response...
[on_prompt_pending hook fires]
```

**Claude Code terminal (with /loop listener):**
```
[LISTENER] Polling session a3f1c9b2
[MCP] Retrieving prompt for session a3f1c9b2...
```

### Phase 5: Verify Flow

1. **Hook fired?**
   ```bash
   tail -f ~/.fcp-entity/.fcp-entity/logs/mcp_notifications.log
   ```
   Should show: `MCP prompt pending: session=a3f1c9b2 file=/home/estupendo/.fcp/pairing/a3f1c9b2.request.json`

2. **Listener triggered?**
   - Check Claude Code terminal for `[LISTENER] Polling session` message
   - Or check if fcp_poll was called

3. **Marker file created?**
   ```bash
   ls -la ~/.fcp-entity/notifications/mcp/
   ```
   Should see `a3f1c9b2.pending` file

4. **Named pipe signaled?**
   ```bash
   ls -la ~/.fcp-entity/signals/
   ```
   Should see `mcp_wake` named pipe (p flag = pipe)

### Phase 6: Complete the Cycle

1. Listener should automatically call `fcp_poll`
2. You should receive the prompt in Claude Code
3. Process the prompt and call `fcp_respond`
4. FCP continues the session

---

## Expected Behavior

### Success Criteria

- [ ] Hook fires when FCP calls `invoke()`
- [ ] Marker file appears in `.fcp-entity/notifications/mcp/`
- [ ] Named pipe receives session_id
- [ ] `/loop` listener triggers automatically
- [ ] `fcp_poll` is called without manual input
- [ ] Prompt arrives in Claude Code
- [ ] Session completes normally

### Logging

Monitor these files during test:

```bash
# Terminal 1: Hook logs
tail -f ~/.fcp-entity/.fcp-entity/logs/mcp_notifications.log

# Terminal 2: MCP server logs (if available)
# (fcp-mcp may log to stdout in Claude Code)

# Terminal 3: FCP session
fcp

# Terminal 4: Listener status
/loop 1s bash -c 'echo "Listener alive: $(date)"; ls -1 ~/.fcp-entity/notifications/mcp/*.pending 2>/dev/null | wc -l'
```

---

## Rollback Plan

If something breaks:

1. **Kill listener:**
   ```
   /clear  # stops /loop commands
   ```

2. **Clean up marker files:**
   ```bash
   rm -rf ~/.fcp-entity/notifications/mcp/*.pending
   ```

3. **Clean up named pipes:**
   ```bash
   rm -f ~/.fcp-entity/signals/mcp_wake
   ```

4. **Restart FCP session:**
   ```bash
   fcp  # should start fresh
   ```

---

## Next Steps After Success

1. **Document findings** in DEV-NOTES.md
2. **Commit any changes** made during testing
3. **Update memory** with lessons learned
4. **Consider making `/loop` persistent** in Claude Code setup
5. **Test with multiple sessions** (parallel FCP instances)

---

## Known Limitations

- ⚠️ `/loop` requires Claude Code to be running
- ⚠️ Listener stops if Claude Code restarts
- ⚠️ Manual listener restart needed after crash
- 🔄 Polling still happens (not event-driven), but at 500ms intervals instead of continuous

---

## Files Involved

```
implementations/fcp-ref/
├── hooks/on_prompt_pending/notify_claude_code      ← Hook (updated)
├── fcp_mcp/CLAUDE_CODE_SETUP.md                    ← Setup instructions
├── test_mcp_loop_integration.sh                    ← Integration test
└── README.md                                        ← Updated with hook info

core-test/
├── .fcp-entity/
│   ├── hooks/                                       ← Hook copied here on init
│   ├── notifications/mcp/                           ← Marker files
│   ├── signals/mcp_wake                             ← Named pipe
│   └── logs/mcp_notifications.log                   ← Hook logs
```

---

## Questions to Answer During Test

1. Does the listener receive signals reliably?
2. Is there any lag between hook firing and fcp_poll being called?
3. Does named pipe work better than directory polling?
4. What's the CPU/memory impact of `/loop`?
5. How does this behave with multiple concurrent sessions?

---

**Ready when you are!** 🚀
