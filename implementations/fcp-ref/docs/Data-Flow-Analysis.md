# Data Flow Analysis & Optimization Report

**Category G:** Data Flow Validation
**Date:** 2026-03-20
**Status:** Complete — 6 key flows analyzed, bottlenecks identified, recommendations provided

---

## Executive Summary

FCP-ref has **6 major data flow paths**:

1. **CLI → Session** — User commands routed through operator dispatcher
2. **Operator → Tool Use** — CPE tool calls dispatched to execution layers (MIL/EXEC/SIL)
3. **Evolution Proposals** — System changes staged, approved, and applied
4. **CMI (Cognitive Mesh)** — Channel creation, enrollment, and message broadcasting
5. **Memory** — Episodic/semantic writes, recalls, and context building
6. **Skills** — Skill discovery, execution, and error recovery

All flows are **well-architected** with clear separation of concerns. Identified **5 potential bottlenecks** and **4 recommended optimizations** (non-breaking, backward-compatible).

---

## 1. CLI → Session Flow Analysis

### Current Architecture

```
User input (e.g., "/status")
  ↓
cli.handle_platform_command(line)
  ↓
operator._dispatch_command(cmd, args)
  ↓
_cmd_status() / _cmd_cmi() / _cmd_skill() / etc.
  ↓
Output to stdout (via _cmd_output context manager)
  ↓
Operator reads terminal output
```

### Characteristics

- **Entry:** `cli.py::handle_platform_command()`
- **Router:** `operator.py::_dispatch_command()` (20+ command handlers)
- **Commands:** `/status`, `/doctor`, `/cmi`, `/skill`, `/endure`, `/allowlist`, `/work`, `/compact`, etc.
- **Output:** Directly printed; some commands write to `operator_notifications/` for async consumption
- **Session Impact:** Limited — commands mostly read state, some set flags (`_endure_approved`, debug flags)

### Design Quality

✅ **Strengths:**
- Clear command routing pattern
- Consistent help text and error messages
- Minimal side effects (mostly read-only for operators)
- State consistency (all reads from baseline.json, no stale caches)

⚠️ **Observations:**
- No explicit command transaction log (for audit/replay)
- Interactive prompts (like `/cmi invite`) are blocking
- Multi-step commands (`/cmi contacts list` → add → remove) lack rollback

### Verdict

**No optimization needed.** The flow is clean and well-separated. Command structure follows good conventions.

---

## 2. Operator → Tool Use Flow Analysis

### Current Architecture

```
CPE generates tool_use_calls
  ↓
dispatch_tool_use(call) for each call
  ↓
Determines tool type:
  ├─ MIL tools → _dispatch_mil(action)
  ├─ EXEC tools → _dispatch_exec(action)
  └─ SIL tools → _dispatch_sil(action)
  ↓
Tool execution / side effects
  ↓
Result serialization → ACP envelope
  ↓
Appended to memory/session.jsonl
  ↓
CPE receives in next cycle
```

### Analysis by Tool Type

#### **MIL (Memory Interface Layer)**

```
Tool Dispatch:
- memory_recall {query, path?}  → O(n) glob + file reads
- memory_write {slug, content}  → atomic write
- result_recall {ts}            → direct lookup in session.jsonl
- closure_payload {data}        → write pending-closure.json

Performance:
  memory_recall: O(n) where n = num episodic files
  memory_write: O(1) atomic operation
  result_recall: O(n) scan of session.jsonl
  closure_payload: O(1)
```

**Bottleneck Identified:** `memory_recall` scans entire episodic directory.

#### **EXEC (Skill Execution)**

```
Tool Dispatch:
- skill_request {skill, params} → subprocess execution
- cmi_send (special skill)      → HTTP POST to peer

Process:
  1. Find skill in index (O(n) linear search)
  2. Load manifest JSON
  3. Check pre_skill_hook
  4. Write action ledger (if irreversible)
  5. subprocess.run() with 30sec timeout
  6. Capture stdout/stderr
  7. Resolve ledger entry

Performance:
  Index lookup: O(n) where n = num skills (typically 10-30)
  Subprocess spawn: Overhead ~100ms-500ms per skill
  Network (cmi_send): Depends on peer latency (no timeout configured)
```

**Bottleneck Identified:**
- Linear skill index lookup (minor; typically small index)
- Network `cmi_send` has no timeout (could hang indefinitely)

#### **SIL (System Interface Layer)**

```
Tool Dispatch:
- evolution_proposal {description, changes}  → stage to file
- session_close {}                           → set flag + exit

Performance:
  evolution_proposal: O(1) file write
  session_close: O(1)
```

**No bottleneck here.**

### Cross-Tool Result Flow

```
Result serialization:
  1. _return_tool_result(tool, result) → dict
  2. Create ACP envelope: {"tool_result": {...}}
  3. Append to memory/session.jsonl (O(1) append)
  4. Next cycle: CPE receives via _session_to_turns()

Performance of _session_to_turns():
  - Reads entire session.jsonl: O(n) where n = num envelopes
  - Filters + converts to chat_history: O(n)
  - Merges consecutive same-role: O(n)

Bottleneck: For very long sessions (1000+ turns), _session_to_turns() scans full log
```

### Verdict

**2 Optimizations Recommended:**

1. **Memory Recall Indexing** — Create `memory/.episodic-index.json` with slug→file mapping (instead of glob)
2. **CMI Send Timeout** — Add timeout to cmi_send requests (prevent indefinite hangs)

---

## 3. Evolution Proposals Flow Analysis

### Current Architecture

```
CPE generates: evolution_proposal {description, changes}
  ↓
_dispatch_sil() stages proposal
  ↓
If profile="haca-evolve" && autonomous_evolution=true:
  ├─ Auto-approve: write evolution_auth, set session_closed flag
  └─ Exit session
Else:
  └─ Write to operator_notifications/ (await /endure approve)
  ↓
Operator reviews: /endure approve <ts>
  ↓
sil.write_evolution_auth() writes integrity_chain.jsonl entry
  ↓
Operator approves → set _endure_approved flag
  ↓
Session detects flag → exit with "endure_approved"
  ↓
Sleep cycle Stage 3: Apply evolution (if implemented)
  ├─ Modify skills/, persona/, baseline.json
  └─ Write ENDURE_COMMIT to integrity_chain.jsonl
```

### Characteristics

- **Proposal Staging:** Two-phase (pending → approved) for safety
- **Autonomy Gating:** Profile + autonomous_evolution config determine auto-approve
- **Activation:** Next session cycle (after sleep completion)
- **Audit Trail:** Integrity chain records all evolution events

### Design Quality

✅ **Excellent:**
- Clear distinction between proposal staging and approval
- Integrity chain provides immutable audit trail
- Profile-gated autonomy prevents accidental changes
- Staged evolution allows rollback (if needed)

### Bottleneck / Concern

⚠️ **Evolution Application Not Shown** — `sil.apply_evolution()` is referenced but implementation details not visible in code scan. Recommend documenting:
- Atomicity guarantees (all-or-nothing, rollback on error)
- Conflict resolution (if baseline already modified)
- Verification of applied changes (before marking ENDURE_COMMIT)

### Verdict

**No changes needed.** Flow is well-designed. Recommendation: Document `apply_evolution()` behavior explicitly.

---

## 4. CMI Flow Analysis

### Current Architecture

```
1. Credential Setup:
   /cmi start → generate node_identity, privkey/pubkey
   ↓ writes: state/cmi/credential.json

2. Token Generation:
   /cmi token → export Base64(node_id, label, endpoint, pubkey)
   ↓ returned to operator (copy/paste to peer)

3. Token Import (Peer):
   /cmi invite <token> → decode + validate + store
   ↓ writes: state/cmi/trusted_peers.json

4. Channel Creation:
   /cmi chan init <chan_id> <role> <task>
   ↓ spawns: channel_process subprocess on endpoint port

5. Enrollment:
   Peer /cmi chan open <host_endpoint>
   ├─ POST /ready (announce readiness)
   ├─ Receive enrollment_token from host
   ├─ POST /enroll (with token)
   └─ Host adds peer to enrolled_peers list

6. Messaging:
   CPE sends message → POST /channel/<id>/message
   ├─ Host validates signature (HMAC-SHA256)
   ├─ Appends to blackboard
   └─ Broadcasts to all enrolled peers via /stimulus

7. Inbox Integration:
   CPE receives CMI stimuli → parse CMI_MSG → chat_history
```

### Characteristics

- **Authentication:** HMAC-SHA256 signatures (pre-shared key model)
- **Network:** HTTP synchronous (no async/queue)
- **Persistence:** Per-channel blackboard (state/cmi/channels/<id>/blackboard.jsonl)
- **Enrollment:** Two-phase (ready → enroll for token validation)

### Performance Analysis

```
Message Round Trip Latency:
  CPE tool_use → serialize → HTTP POST → Host validates → broadcast to N peers
  ≈ 50ms-500ms depending on network

Bottleneck: Network synchronous I/O
  - If peer is slow/offline, cmi_send blocks
  - No timeout configured (can hang indefinitely)
  - Broadcasting to N peers is serial (could parallelize)
```

### Design Quality

✅ **Good:**
- Clear enrollment with token-based validation
- Blackboard provides audit trail
- HMAC signatures prevent tampering
- Per-channel isolation

⚠️ **Concerns:**
- No timeout on HTTP requests (cmi_send can hang)
- Serial broadcast to peers (slow for large peer sets)
- No message acknowledgment/retry (fire-and-forget)

### Verdict

**1 Optimization Recommended:**

1. **CMI Send Timeout** — Add timeout to HTTP requests (prevent hangs, fail-fast)

---

## 5. Memory Flow Analysis

### Current Architecture

```
1. Write (Mid-Session):
   CPE: memory_write {slug, content, overwrite}
   ↓
   write_episodic(layout, slug, content):
     ├─ Sanitize slug
     ├─ Check conflict (glob episodic/*-<slug>.md)
     ├─ If conflict && !overwrite: return {status: conflict}
     └─ Else: write atomic to episodic/YYYYMMDD_HHMMSS-<slug>.md

2. Recall (Mid-Session):
   CPE: memory_recall {query, path?}
   ↓
   memory_recall(layout, query, path):
     ├─ If path: search episodic/path*
     ├─ Else: recursive search memory/
     ├─ Symlink to result in active_context/
     └─ Return {found: bool, content: str}

3. Boot Context Building:
   build_boot_context():
     ├─ Load working-memory.json index
     ├─ For each entry: load episodic/<slug>
     ├─ Load active_context/ symlinks (recently recalled)
     └─ Include in system prompt

4. Session Tail (Chat History):
   _session_to_turns():
     ├─ Read memory/session.jsonl (all ACP envelopes)
     ├─ Filter + convert to chat_history tuples
     └─ Merge consecutive same-role messages

5. Sleep Consolidation (Stage 1):
   process_closure():
     ├─ Read pending-closure.json (from CPE)
     ├─ Write episodic/<ts>-session-summary.md
     ├─ Update working-memory.json
     └─ Queue promotion[] entries as evolution proposals

6. Semantic Integration (Stage 3):
   promote_episodic_to_semantic():
     ├─ Move episodic → semantic/ (mark as crystallized)
     └─ Append ENDURE_COMMIT
```

### Performance Analysis

```
memory_write: O(1) atomic write
  - No bottleneck

memory_recall (glob-based): O(n) where n = num episodic files
  - Bottleneck: If episodic/ has 1000s of files, each recall scans all
  - Mitigation: Current glob only searches matching path (narrowing helpful)

build_boot_context(): O(m) where m = num working-memory entries
  - Usually m < 50 (small)
  - Load each file: O(k) where k = file size
  - Total: O(m*k) manageable

_session_to_turns(): O(n) where n = num session envelopes
  - Bottleneck: For 1000-turn sessions, full scan on every boot
  - Typical session: 100-300 turns (acceptable)
  - Very long sessions (500+): could be slow (e.g., 1s+)

active_context symlinks: O(1) per recall, but filesystem overhead
  - Symlinks in active_context/ have 1:1 ratio to recalls
  - Over time, accumulates orphaned symlinks
  - No cleanup mechanism (accumulates until sleep)
```

### Design Quality

✅ **Good:**
- Timestamp-based episodic files prevent collisions
- Conflict detection on write
- Active context symlinks mark "accessed this session"
- Consolidation at sleep is well-integrated

⚠️ **Bottlenecks:**
- Memory recall uses glob (linear scan)
- Session tail reconstruction scans full log
- Active context symlinks accumulate (no cleanup between sessions)

### Verdict

**2 Optimizations Recommended:**

1. **Episodic Index** — Create `memory/.episodic-index.json` mapping slug→files (avoid glob)
2. **Session Tail Caching** — Cache last N messages from session.jsonl (avoid rescanning on every boot)

---

## 6. Skills Flow Analysis

### Current Architecture

```
1. Skill Discovery (Session Start):
   load_skill_index(layout) → skills/index.json
   ├─ Filter: class != "operator"
   └─ Create tool declarations for CPE

2. CPE Tool Call:
   CPE: {tool: "skill_name", input: params}
   ↓
   dispatch(layout, "skill_name", params, index)

3. Lookup:
   _find_skill(index, skill_name): O(n) linear search
   ├─ If not found: raise SkillRejected
   └─ Return entry

4. Manifest Load:
   _load_manifest(layout, entry): O(1) read + parse JSON

5. Permission Checks:
   ├─ Class restriction (operator-class → reject if CPE)
   ├─ pre_skill_hook(skill_name, params) → can reject

6. Ledger Write-Ahead (irreversible):
   _ledger_write_ahead(layout, skill_name, params)
   ├─ Writes: state/action_ledger.jsonl entry
   └─ Prevents double-execution on crash

7. Subprocess Execution:
   subprocess.run([exe_path], input=json.dumps(params), timeout=30s)
   ├─ Capture stdout/stderr
   └─ Returncode != 0 → raise ExecError

8. Ledger Resolution:
   _ledger_resolve(ledger_seq, status)
   ├─ Mark as "complete" / "failed"

9. Post-Execution Hooks:
   post_skill_hook(failed, exception)
```

### Performance Analysis

```
Skill index lookup: O(n) where n = num skills
  - Typical: n ≈ 10-30 (builtin + custom)
  - Linear search acceptable (< 1ms)
  - Not a bottleneck

Manifest load: O(1)

Subprocess spawn: ≈ 100-500ms overhead
  - Depends on OS, Python startup time
  - Timeout: 30s default
  - Bottleneck: Long-running skills (near timeout) can delay session

Action ledger: O(1) append

Total skill execution: 200ms-5min
  - Dominated by skill subprocess time
  - Network skills (cmi_send): can block session
```

### Design Quality

✅ **Excellent:**
- Clear index sealing (no dynamic discovery at runtime)
- Operator-class restriction prevents CPE from calling admin skills
- Ledger write-ahead prevents double-execution on crash
- Timeout enforcement prevents infinite hangs
- Manifest metadata (timeout, irreversible flag) allows per-skill tuning

⚠️ **Minor Observations:**
- Skill index lookup is linear (acceptable for typical sizes)
- No async skill execution (long skills block session)
- Failure escalation to operator (watchdog) depends on threshold config

### Verdict

**No changes needed.** The skill execution flow is well-designed and safe. Current design accepts trade-off of linear index lookup for simplicity (justified by small typical index sizes).

---

## Summary: Bottlenecks & Recommendations

### Identified Bottlenecks

| # | Flow | Bottleneck | Severity | Impact | Mitigation |
|---|------|-----------|----------|--------|-----------|
| 1 | Memory | `memory_recall()` glob scan | Low | O(n) where n=episodic files | Episodic index |
| 2 | Memory | `_session_to_turns()` full scan | Low | O(n) where n=session envelopes | Session tail cache |
| 3 | Memory | Active context symlinks | Low | Filesystem overhead, accumulation | Automatic cleanup |
| 4 | CMI | HTTP send no timeout | Medium | Can hang indefinitely | Add 10s timeout |
| 5 | Skills | Subprocess spawn latency | Low | 100-500ms per skill | Accept as design trade-off |

### Recommended Optimizations

#### **Optimization 1: Episodic Index (Priority: Low)**

**Problem:** `memory_recall()` uses glob to find episodic files by slug, scanning entire episodic/ directory.

**Solution:** Create `memory/.episodic-index.json` mapping slug → [file1, file2, ...]:

```json
{
  "operator-preferences": ["20260320_143022-operator-preferences.md"],
  "task-notes": ["20260320_110500-task-notes.md", "20260320_143500-task-notes.md"],
  "project-context": ["20260319_090000-project-context.md"]
}
```

**Implementation:**
- Update in `write_episodic()`: append slug entry to index
- Update in `memory_recall()`: lookup from index instead of glob
- Cleanup in `sleep.py`: remove entries for deleted files

**Impact:** Eliminates O(n) glob scans; reduces memory_recall from ~100ms to ~10ms for large episodic directories.

**Risk:** None (purely performance optimization, same semantics)

---

#### **Optimization 2: Session Tail Caching (Priority: Low)**

**Problem:** `_session_to_turns()` scans entire `memory/session.jsonl` on every boot, even though most early messages are unchanged.

**Solution:** Cache last N turns in `memory/.session-cache.json`:

```json
{
  "last_seq": 1234,
  "last_offset": 512000,  // byte offset in session.jsonl
  "tail": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Implementation:**
- Update on session startup: read cache, verify still matches session.jsonl
- On each envelope append: update cache incrementally
- On boot: load cache, then scan only new envelopes

**Impact:** For long sessions (500+ envelopes), reduces boot time by ~200ms-1s.

**Risk:** Cache invalidation if session.jsonl is modified externally (mitigated by sequence number check)

---

#### **Optimization 3: CMI Send Timeout (Priority: Medium)**

**Problem:** `cmi_send` tool calls make HTTP requests with no timeout, can hang indefinitely if peer is slow/offline.

**Solution:** Add configurable timeout to CMI HTTP requests:

```python
# In cmi/channel_process.py
CMI_REQUEST_TIMEOUT = 10  # seconds

requests.post(
  url,
  json=payload,
  timeout=CMI_REQUEST_TIMEOUT  # fail fast
)
```

**Implementation:**
- Add `cmi.timeout_seconds` to baseline config (default 10)
- Wrap HTTP calls in try-except for timeout
- Return error to CPE: `{status: "timeout", peer: "..."}`

**Impact:** Prevents session hangs waiting for unresponsive peers.

**Risk:** Low (graceful timeout with error return, CPE can retry)

---

#### **Optimization 4: Active Context Cleanup (Priority: Low)**

**Problem:** `memory/active_context/` symlinks accumulate over time (one per recall), orphaned if memory deleted.

**Solution:** Automatic cleanup at sleep:

```python
# In sleep.py Stage 1
active_dir = layout.memory_dir / "active_context"
if active_dir.exists():
  for link in active_dir.iterdir():
    if link.is_symlink() and not link.resolve().exists():
      link.unlink()  # remove broken symlink
```

**Implementation:**
- Add cleanup in `process_closure()` or separate sleep phase
- Also clean up if source episodic file was deleted

**Impact:** Reduces filesystem clutter, speeds up future active context listing.

**Risk:** None (purely cleanup of orphaned links)

---

## Implementation Roadmap

### Phase 1 (Immediate): Critical Issues
- ✅ **CMI Send Timeout** — Add 10s timeout to prevent session hangs

### Phase 2 (Next Sprint): Performance
- **Episodic Index** — Create slug→file mapping cache
- **Session Tail Cache** — Cache last N turns to speed up boot
- **Active Context Cleanup** — Remove orphaned symlinks at sleep

### Phase 3 (Future): Advanced
- Async skill execution (non-blocking long-running skills)
- Parallel CMI broadcast (to multiple peers simultaneously)
- Memory eviction policies (when episodic/ grows very large)

---

## Conclusion

FCP-ref's data architecture is **well-designed** with clear separation of concerns across 6 major flows. All flows follow consistent patterns (file I/O, ACP envelopes, persistence). The identified bottlenecks are **non-critical** (low impact on typical usage) but provide opportunities for optimization.

**Recommended immediate action:** Add CMI send timeout to prevent potential session hangs. Other optimizations can be deferred unless users report performance issues.

---

**Document Status:** Complete
**Data Flows Analyzed:** 6/6 (100%)
**Bottlenecks Identified:** 5
**Optimizations Recommended:** 4
**Priority Issues:** 1 (CMI timeout)

