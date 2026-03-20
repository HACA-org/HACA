# commit

Safe git operations within `workspace_focus`. This is the only version-control interface available to the CPE — direct git access via `shell_run` is rejected.

**Supported commands:** `init`, `add`, `commit`, `status`, `log`, `diff`, `branch`, `checkout`, `config`, `push`

## Safety Model

✅ **Safe (no gating required):**
- `init` — initialize git repo
- `add` — stage files
- `commit` — create commits
- `status` — view changes
- `log` — view history
- `diff` — view diffs
- `branch` — create/list local branches
- `checkout` — switch branches
- `config` — set user.name/user.email only

⚠️ **Gated (requires authorization):**
- `push` — requires `force_confirm: true` parameter

❌ **Blocked:**
- Force push, reset --hard, rebase -i, clone — not exposed

## Examples

```javascript
// Initialize repo
commit({ "command": "init" })

// Stage and commit
commit({ "command": "add", "path": "notes.md" })
commit({ "command": "commit", "message": "add notes" })

// View history
commit({ "command": "log", "limit": 20 })
commit({ "command": "status" })

// Branch management
commit({ "command": "branch", "action": "list" })
commit({ "command": "branch", "action": "create", "name": "feature/x" })
commit({ "command": "checkout", "branch": "feature/x" })

// Config
commit({ "command": "config", "key": "user.name", "value": "Entity" })

// Push (requires confirmation)
commit({ "command": "push", "force_confirm": true })
```

## Parameters

### All commands
- `command` (required) — git command: `init`, `add`, `commit`, `status`, `log`, `diff`, `branch`, `checkout`, `config`, `push`

### By command

**init**
- `path` (optional) — directory to initialize. Default: `workspace_focus`

**add**
- `path` (required) — file/dir within `workspace_focus` to stage

**commit**
- `message` (optional) — commit message. Default: `"checkpoint"`

**log**
- `limit` (optional) — number of commits to show. Default: `10`

**diff**
- `path` (optional) — file/dir to diff. Default: entire repo

**branch**
- `action` (optional) — `"list"` (default) or `"create"`
- `name` (required if action="create") — branch name

**checkout**
- `branch` (required) — branch name to switch to

**config**
- `key` (required) — `"user.name"` or `"user.email"` only
- `value` (required) — config value

**push**
- `force_confirm` (required) — must be `true` to authorize push

## Notes

- Requires `workspace_focus` to be set (except `init` with explicit path).
- All paths must be within `workspace_focus` or outside entity root entirely.
- Cannot access entity repo or parent directories.
- Entity cannot create/modify `.git/config` globally — only local config allowed.
