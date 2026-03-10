# FCP: Filesystem Cognitive Platform
**Status:** Internet-Draft  
**Version:** 1.0-Draft-04
  
**Authors:** J. Orrico  
**Date:** February 25, 2026

---

## Abstract

The Filesystem Cognitive Platform (FCP) is the reference implementation of the Host-Agnostic Cognitive Architecture (HACA). It builds a fully compliant autonomous cognitive system using nothing but standard POSIX filesystem primitives.

**No external databases. No daemon processes. No complex registries.**

An FCP entity is a single directory. Its entire cognitive state — identity, memories, agenda, skills — lives in plain text files. You can clone an AI entity by copying its directory to a USB drive. You can version-control an entity's evolution with `git`. You can inspect its thoughts by running `cat`.

The filesystem is the application.

---

## 1. Overview and "Living off the Land"

FCP implements HACA's four-layer architecture (see [HACA-Arch](../../spec/HACA-Arch-1.0.0.md)) using filesystem primitives:

| HACA Layer | FCP Implementation |
|---|---|
| Memory Interface Layer (MIL) | `/memory/` directory tree |
| Cognitive Processing Engine (CPE) | LLM invoked via BOOT.md prompt |
| Execution Layer (EL) | Scripts in `/skills/` cartridges |
| System Integrity Layer (SIL) | Host daemon orchestrating boot phases |

The key insight is that the POSIX filesystem already provides most of what HACA needs:

- **`rename(2)` is atomic** within a filesystem → crash-safe writes
- **`O_APPEND` writes ≤ 4KB are atomic** → lockless concurrent logging
- **Symbolic links** → dynamic, O(1) context switching (Symlink VRAM)
- **`readdir(3)` returns sorted entries** → deterministic context assembly
- **File permissions** → primitive access control for skills

---

## 2. The File Format Triad

FCP restricts the system to three file extensions. This constraint keeps the format simple, auditable, and tool-friendly:

| Extension | Purpose | Characteristics |
|---|---|---|
| `.md` (Markdown) | Read-only identity context (persona, boot instructions) | Immutable at runtime; human-readable |
| `.jsonl` (JSON Lines) | All transactional state (memory, events, agenda) | Append-only; each line is an atomic, integrity-verifiable record |
| `.json` (JSON) | Static configuration (capability manifests, integrity hashes) | Written via safe write-to-temp + atomic rename; never appended |

**Why JSON Lines for memory?** Because each line can be parsed independently — a corrupt line affects only itself, not the entire log. And because `O_APPEND` writes up to 4KB are atomic on POSIX systems, multiple actors can write to the same `.jsonl` file concurrently without a lock.

---

## 3. Directory Topology

An FCP-compliant entity is entirely encapsulated within a single root directory:

```
/                             ← Entity root (copy this directory = clone the entity)
├── BOOT.md                   ← Boot Protocol: the LLM's instruction manual
├── .gitignore                ← Excludes volatile state from version control
│
├── persona/                  ← Core Identity (THE ENTITY'S SOUL)
│   ├── identity.md           ← Who the entity is
│   ├── values.md             ← What it cares about
│   └── constraints.md        ← What it must never do
│
├── state/                    ← SIL operational files
│   ├── integrity.json        ← SHA-256 hashes of all immutable files
│   ├── drift-probes.jsonl    ← Canonical behavioral test set
│   ├── agenda.jsonl          ← Scheduled task queue (append-only)
│   ├── env.md                ← Volatile host environment snapshot
│   ├── rotation.journal      ← Write-ahead log for atomic log rotations
│   └── sentinels/            ← Dynamic Sentinel Streams (runtime counters, 
│                             ← sequence state) separate from static identity
│
├── hooks/                    ← Lifecycle scripts (operator-only, validated at boot)
│
├── skills/                   ← Execution Layer: pluggable capabilities
│   ├── index.json            ← RBAC capability registry
│   └── <skill_name>/
│       ├── SKILL.md          ← What the skill does (for the LLM to read)
│       └── manifest.json     ← Machine-readable capability declaration
│
├── memory/                   ← Memory Interface Layer
│   ├── inbox/                ← Incoming results from the EL (atomic rename target)
│   ├── spool/                ← Actor-private temporary write area
│   ├── session.jsonl         ← Main session log: the current conversation/cycle
│   ├── active_context/       ← Symlinks to currently "loaded" memory fragments
│   ├── concepts/             ← Semantic Graph via .link files (Section 7.1)
│   ├── archive/              ← Older session fragments (hot storage)
│   └── cold_storage/         ← Compressed archives (moved rarely)
│
├── workspaces/               ← Sandboxed execution environment for skills
└── snapshots/                ← Point-in-time MIL backups for rollback
```

**The most important rule:** Files in `persona/` are **immutable at runtime**. The CPE cannot modify them. The SIL verifies their cryptographic hashes at every boot. If any of them change between boots, the system refuses to start.

Everything else in the tree can evolve — but `persona/` defines the bedrock identity of the entity.

---

## 4. The ACP Envelope Format

All transactional data in `.jsonl` files uses the ACP (Atomic Chunked Protocol) envelope format. Every line in `session.jsonl` or `agenda.jsonl` is a JSON object with this schema:

```json
{
  "actor":  "supervisor",
  "gseq":   4207,
  "tx":     "uuid-1234-5678-abcd",
  "seq":    1,
  "eof":    true,
  "type":   "MSG",
  "ts":     "2026-02-22T18:30:00Z",
  "data":   "The actual payload content goes here.",
  "crc":    "a1b2c3d4"
}
```

| Field | Purpose |
|---|---|
| `actor` | Who wrote this envelope (e.g., `"supervisor"`, `"sil"`, `"el"`) |
| `gseq` | Global sequence counter — monotonically increasing, per actor |
| `tx` | Transaction UUID — ties multi-chunk messages together |
| `seq` | Sequence number within the transaction (1-indexed) |
| `eof` | `true` if this is the last chunk of the transaction |
| `type` | Message type (see below) |
| `ts` | ISO 8601 UTC timestamp |
| `data` | The payload (UTF-8 string; structured payloads are JSON-serialized into this field) |
| `crc` | CRC-32 of `data` — detects accidental corruption; 8-char lowercase hex |

**The 4KB Rule:** No single ACP envelope may exceed 4000 bytes. Larger payloads are chunked across multiple envelopes sharing the same `tx`, with incrementing `seq` and `eof: true` on the final chunk.

**Common envelope types:** `MSG`, `SKILL_REQUEST`, `SKILL_RESULT`, `SKILL_ERROR`, `SKILL_TIMEOUT`, `SCHEDULE`, `CRON_WAKE`, `DRIFT_PROBE`, `DRIFT_FAULT`, `TRAP`, `RECOVERY`, `ROTATION`, `CTX_ADD`, `CTX_SKIP`.

---

## 5. Execution Mechanics and Concurrency

### 5.0. Execution Modes

FCP supports two execution modes. The mode is detected at boot (Phase 0) and recorded in `state/env.md`.

**Transparent Mode** — the SIL is the adapter:
```
SIL → assembles context → calls LLM API → parses fcp-actions → executes
```
The LLM emits a structured `fcp-actions` block in its response. The SIL reads it and dispatches each intent to the EL. This is the default mode for API-based deployments.

**Opaque Mode** — the CPE is the adapter (IDE assistants, agents with native filesystem tools):
```
CPE reads BOOT.md → detects native tools → acts directly via tool calls
```
When the CPE has direct filesystem access (e.g., Claude Code, Cursor, Copilot Workspace), it maps each intent to a native tool call (`Write`, `Bash`, etc.). It still emits `fcp-actions` blocks as an audit trace, but native calls are what execute — the SIL is not required.

**Both modes are semantically identical.** Memory, skills, and identity operate the same way. The `fcp-actions` protocol is a mode-agnostic intent description; the executing adapter (SIL or CPE) maps it to real operations. This design allows FCP to run in any environment without requiring API bindings.

**Adapter Contract** — invariants that apply in both modes:
- RBAC validation: only skills listed in `skills/index.json` may be invoked
- Results are committed to the MIL before being referenced in subsequent cycles
- `persona/` and immutable files may not be mutated by the CPE
- Single ACP envelope ≤ 4KB
- EL writes are restricted to declared sandbox paths

FCP uses two cooperating processes:

**The SIL/Host Daemon** — a lightweight script or daemon that:
- Watches for triggers (cron events, file-watcher notifications, user input)
- Manages the boot sequence
- Assembles the CPE's context
- Consolidates the inbox into `session.jsonl`

**The Cognitive Runtime (CPE invocation)** — runs once per cognitive cycle:
- Receives the assembled context
- Invokes the LLM (local or API)
- Parses the LLM's structured output for state deltas and Side-Effect requests
- Shuts down after writing outputs to the spool

### 5.1. Lockless Spooling

The core concurrency primitive that makes FCP work without database locks:

```
Actors (EL, SIL, CPE output handler)
│
├── Write to private temp file:
│   /memory/spool/<actor>/<timestamp>-<seq>.tmp
│   (If write fails partway, the .tmp file is simply discarded)
│
└── When write is complete + fsynced:
    Atomic rename → /memory/inbox/<timestamp>-<seq>.msg
    (rename(2) is atomic: file is either there or not, never partial)

SIL periodically:
└── Reads all .msg files from /memory/inbox/ in order
    └── Appends each to session.jsonl
    └── Unlinks the .msg file
```

This pattern (inspired by `maildir`) means:
- **No writer blocks another writer.** Everyone writes to their own private temp file.
- **No reader is confused by a partial write.** The file is only visible in `inbox/` after the rename, which is atomic.
- **The SIL is the only writer to `session.jsonl`**, maintaining single-writer discipline on the main log.

---

## 6. Boot Sequence

Every cognitive cycle begins with a deterministic seven-phase boot sequence. Each phase must complete successfully before the next begins. Any failure aborts the boot.

### Phase 0 — Host Introspection
The SIL generates `/state/env.md`: a structured snapshot of the host environment (OS, filesystem type, available binaries, context budget). This file is consumed by the CPE as environmental context.

The SIL also detects the current execution mode (see §5.0) and records it in `env.md`. Crucially, Phase 0 verifies **Active Confinement** capabilities: confirming the presence of native Linux Namespaces (`unshare`) for transparent auto-sandboxing.

**Security note:** `env.md` is a prompt injection vector — it's loaded into the CPE's input. FCP restricts its schema to a fixed set of key-value pairs. No free-text fields. Binary names are basenames only, no full paths.

### Phase 1 — Crash Recovery
The SIL completes any interrupted log rotations (found via `rotation.journal`) and repairs any incomplete ACP envelopes (truncated JSON lines from a crashed write). Incomplete multi-chunk transactions are discarded.

### Phase 2 — Integrity Validation
The SIL reads `state/integrity.json` and recomputes SHA-256 hashes of all immutable files:
- All files in `persona/`
- `BOOT.md`
- `skills/index.json` (the RBAC registry)
- All skill `manifest.json` files
- `.gitignore`
- All files in `hooks/`
- `state/integrity.json` itself (via an external or operator-held anchor)

Any mismatch → **boot aborts**. The entity does not start with a tampered identity.

### Phase 3 — RBAC Resolution
The SIL loads `skills/index.json` and determines which skills are authorized for the current run. Unauthorized skills are excluded from the context.

`skills/index.json` also contains a `.command` alias map — a flat lookup table from operator shorthand (e.g., `.save`, `.snap`) to skill name. Each skill declares its alias in `manifest.json` under `"command"`. When the SIL detects a `.`-prefixed token in operator input, it resolves it via this map and dispatches the skill directly, without involving the CPE.

### Phase 4 — Context Assembly
The SIL assembles the CPE's input context in a deterministic order:

```
[PERSONA]       ← persona/ files, lexicographic order
[BOOT PROTOCOL] ← BOOT.md (the CPE's instruction manual)
[ENV]           ← state/env.md
[SKILLS INDEX]  ← skills/index.json (full RBAC registry and .command alias map)
[SKILL:name]    ← authorized skill manifests, one block each
[MEMORY]        ← symlinks in memory/active_context/, sorted descending by priority prefix
[SESSION]       ← tail of session.jsonl, newest-first until context budget is exhausted
```

Each section uses a delimited marker so the CPE can reliably parse its context. The `[SKILLS INDEX]` section is loaded before individual skill blocks so the CPE has a complete capability map without needing to infer it from individual skill entries. Session history is loaded newest-first; when the context budget is exhausted, older entries are dropped. Every skipped fragment is logged with a `CTX_SKIP` envelope for observability.

### Phase 5 — Drift Probes
The SIL invokes the CPE with each probe from `state/drift-probes.jsonl` and compares actual responses to reference strings using **Unigram NCD** (Normalized Compression Distance). This method ensures robust comparison without external embedding models. If divergence exceeds the configured threshold, a `DRIFT_FAULT` Trap is injected and the boot halts.

Probe responses are **never committed to the MIL** — they are transient verification data consumed only by the SIL.

### Phase 6 — Ignition
The SIL creates a heartbeat lockfile at `/state/pulses/<actor>.alive`. The CPE starts. The lockfile's `mtime` must be updated every ~60 seconds; a stale lockfile (mtime older than ~180 seconds) signals the host that the CPE has crashed.

---

## 6a. First Activation Protocol (FAP)

On a fresh clone, `FIRST_BOOT.md` is present in the root directory. The system detects this file during Phase 0 and enters the **First Activation Protocol** — a one-time cold-start sequence that transforms a "directory of definitions" into a system with lived identity.

**Cold-start detection:** A cold-start occurs when `FIRST_BOOT.md` is present AND `memory/` is empty (no prior session log). Both conditions must be true.

**Why FAP is necessary:** A system with no prior memory has no operator binding, no self-knowledge, and no behavioral baseline. Without FAP, the CPE must rediscover its own capabilities, constraints, and operator context on every session — wasting resources and risking behavioral inconsistency. FAP creates the initial memory scaffold once, and all subsequent boots build on it.

**FAP execution (in order):**
1. **Operator binding** — Collect operator name, handle, and timezone. Write to `memory/preferences/operator.json` via atomic rename. Schema: `{name, handle, contact, timezone, bound_at, actor_id: "supervisor"}`.
2. **Capability introspection** — Read all persona files and authorized skill manifests. Build a working understanding of authorized capabilities and constraints.
3. **Identity consolidation** — Write a self-knowledge document to `memory/concepts/self_analysis.md`. Create a symlink to it in `memory/active_context/` at priority 10 (highest, dropped last).
4. **Activation record** — Append a FAP completion envelope to `memory/session.jsonl` (type: `RECOVERY`, actor: `sil`).
5. **Sentinel removal** — Delete `FIRST_BOOT.md`. Its absence is the durable signal that FAP has completed.

**Drift probes during FAP:** Phase 5 (Drift Probes) MUST be skipped during a cold-start. There is no behavioral baseline yet — running probes would fault unconditionally. After FAP completes, the first warm-boot establishes the baseline.

**FAP failure:** If FAP cannot complete (e.g., operator binding fails, filesystem write fails), `FIRST_BOOT.md` is left in place and an Initialization Fault is declared. The system does not proceed to normal operation.

---

## 7. Symlink VRAM: Vectorless Semantic Paging

This is one of FCP's most distinctive design choices — and it eliminates the need for an external vector database entirely.

Most AI agent frameworks use a heavy semantic retrieval layer (ChromaDB, Pinecone, pgvector) to answer: *"Which past memories are most relevant to the current context?"* FCP replaces this with a much simpler filesystem primitive: **symbolic links**.

### The Active Context Directory

`/memory/active_context/` is a directory containing only symlinks. Each symlink points to a memory fragment in `/memory/archive/` and carries a numeric priority prefix:

```
/memory/active_context/
├── 10-project-alpha.jsonl → ../archive/2026-01/session-1234.jsonl
├── 20-codebase-notes.jsonl → ../archive/2026-02/session-5678.jsonl
└── 90-user-preferences.jsonl → ../archive/2026-01/session-abcd.jsonl
```

Context composition (Phase 4) becomes simply:
```bash
cat /memory/active_context/*
```

The OS reads them in **natively sorted, O(1) linear fashion**, ordered by the numeric prefix. Higher prefix = lower priority (loaded last, dropped first when context is full).

### Loading a memory fragment (Swap In)
```bash
# Link a fragment into active context with priority 20
ln -s ../archive/2026-02/session-5678.jsonl /memory/active_context/20-session-5678.jsonl
```

### Unloading a memory fragment (Swap Out)
```bash
# Remove from active context (the actual file in archive/ remains untouched)
unlink /memory/active_context/20-session-5678.jsonl
```

The CPE can request that specific memories be paged in by emitting a `SKILL_REQUEST` for a memory-retrieval skill. The skill searches the archive (using keyword search, date range, or a lightweight embedding index) and creates the appropriate symlinks. But critically, **the indexing overhead is paid only at retrieval time**, not at every context assembly.

### 7.1. Semantic Graph (Conceptual)
For complex knowledge retrieval, FCP supports a **Semantic Graph** via `.link` files in `/memory/concepts/`. These are plain-text files where each line is a relative path to a memory fragment, allowing the CPE to traverse related concepts without an external vector database.

---

## 8. Cognitive Scheduler (Autonomous Operation)

FCP entities are not purely reactive. They can schedule their own future actions via `state/agenda.jsonl`:

```json
{"actor":"supervisor","tx":"...", "type":"SCHEDULE","ts":"...","eof":true,"seq":1,"gseq":100,
 "data": "{\"cron\": \"0 9 * * 1-5\", \"task\": \"Summarize yesterday's session and update progress notes\"}",
 "crc":"..."}
```

The host cron daemon watches for agenda entries and, when a trigger fires:
1. The SIL injects a `CRON_WAKE` Trap into `session.jsonl`.
2. A full boot cycle begins.
3. The CPE wakes up, sees the CRON_WAKE event, and executes the scheduled task.

This makes the entity **autonomous between user interactions** — it can summarize, archive, self-maintain, and initiate actions without waiting for a human prompt.

---

## 9. Semantic Drift Control

The system monitors its own behavioral fidelity via `state/drift-probes.jsonl`. Each entry is a canonical prompt that the entity should answer consistently with its defined identity:

```json
{"type":"DRIFT_PROBE","data":"{\"prompt\":\"What are your core values regarding user privacy?\",\"expected_embedding\":\"[0.123,0.456,...]\",\"tolerance\":0.12}","..."}
```

At each drift probe run:
1. The SIL submits each probe prompt to the CPE with `temperature=0` (deterministic).
2. The actual response is compared to the stored reference text using Unigram NCD.
3. The average divergence across all probes is the drift score.
4. If drift score > threshold (default: 0.15), a `DRIFT_FAULT` Trap is injected and the system enters read-only mode.

**What causes drift?** Primarily: model updates from the LLM provider, accumulated adversarial inputs in the session history, or corrupted identity files. The probe set detects all of these at the behavioral level, regardless of cause.

**What happens in read-only mode?** The CPE can still respond to user queries (the user can interact with the entity), but:
- No state is committed to `session.jsonl`
- No EL actions are executed
- The agenda is suspended

This prevents a drifted entity from writing corrupted memories or taking harmful actions until an operator reviews the situation.

---

## 10. Security Model

### Capability Sandboxing
Every skill must be declared in `skills/index.json` before it can be loaded. Each skill's `manifest.json` specifies exactly what it can do:

```json
{
  "name": "web_search",
  "capabilities": ["http_get"],
  "security": {
    "max_tokens_output": 4000,
    "allowed_domains": ["*.wikipedia.org", "*.github.com"]
  }
}
```

The EL validates every Side-Effect request against the manifest before executing it. A CPE that requests `"run arbitrary shell command"` will find no skill in the registry with that capability, and the request will be silently rejected and logged.

### Integrity Anchoring
`state/integrity.json` maps each immutable file to its SHA-256 hash:

```json
{
  "version": "1.0",
  "algorithm": "sha256",
  "signatures": {
    "BOOT.md": "a1b2c3d4e5f6...",
    "persona/identity.md": "e3b0c44298fc...",
    "skills/index.json": "8d969eef6eca..."
  }
}
```

This file itself must be protected — in a production deployment, its hash should be stored separately (e.g., a hardware TPM, an operator-held pre-shared hash, or a signed commit in a read-only branch).

### Sandbox Verification
During Phase 0 (Host Introspection), the SIL actively verifies its own **Active Confinement** boundary:
- Confirms `unshare` utility is functional.
- Verifies capability to mapped root user within namespaces.
- Fallback (if Namespaces unavailable): Attempts a write outside `/workspaces/` and a read outside the FCP root — must fail.

If verification fails, the entity enters degraded mode: the CPE can respond to queries but no EL actions are permitted. This ensures the isolation boundary is validated before the entity begins any autonomous operation.

---

## 11. Log Rotation

When `session.jsonl` grows past a configurable size limit (default: 2 MB), the SIL performs a crash-safe rotation:

```
1. Acquire rotation lock:  O_CREAT|O_EXCL on /state/rotation.lock
   (Atomic: either you created it or another process did — no ambiguity)

2. Write intent to /state/rotation.journal  (fsync)

3. Atomic rename:  session.jsonl → archive/2026-02/session-<timestamp>.jsonl

4. Create new empty session.jsonl

5. Delete rotation.journal entry  (fsync)

6. Remove rotation.lock
```

If the SIL crashes between steps 2 and 5, it finds `rotation.journal` at next boot and completes the interrupted rotation before proceeding. This write-ahead log pattern ensures that a rotation is never lost or left in an inconsistent state.

---

## 12. Portability and Version Control

### Cloning an Entity
```bash
cp -r /path/to/entity /path/to/clone
```
That's it. The clone starts with identical identity, memories, skills, and agenda. From boot, it's an independent entity.

### Version-Controlling an Entity's Evolution
```bash
cd /path/to/entity
git init
# FCP includes a protected .gitignore that excludes volatile state:
#   /memory/session*.jsonl
#   /state/pulses/
#   /state/agenda.jsonl
#   /state/env.md
#   /workspaces/
git add .
git commit -m "Entity v1: initial persona and skill set"
```

Because the entity's identity and skills are plain text, you get a full `git log` of every deliberate evolution of the entity. The `persona/` files, `skills/`, and `state/drift-probes.jsonl` are all versioned. Volatile runtime state is excluded.

### Self-Evolution via `sys_endure`

`sys_endure` is the **sole gatekeeper** for all changes to files tracked in `state/integrity.json`. No tracked file may be modified through any other path at runtime.

It operates as a protocol with subcommands:

| Subcommand | What it does |
|---|---|
| `add skill` | Scaffold skill dir + manifest + script, register in `skills/index.json`, seal |
| `add hook` | Create hook script under `hooks/<event>/`, seal |
| `evolve identity` | Propose `persona/` change → run drift probes → apply if pass → seal |
| `evolve boot` | Propose `BOOT.md` change → apply → seal |
| `remove skill` | Unregister from `skills/index.json`, unseal, delete (requires `--confirm`) |
| `remove hook` | Unseal, delete (requires `--confirm`) |
| `seal` | Recompute SHA-256 for all tracked files, update `state/integrity.json` atomically |
| `sync` | `git commit` all staged evolution changes. `--remote` also pushes. |
| `status` | Compare current file hashes against sealed values — shows MODIFIED/MISSING |

**Every operation follows this protocol:**
1. Create a point-in-time snapshot (pre-mutation backup)
2. Execute the operation-specific handler
3. Call `seal` — recompute and update `state/integrity.json`
4. Emit an ACP audit envelope to `memory/session.jsonl`
5. (Deferred) `sync` — commit to git when the operator is ready

The `evolve identity` subcommand is the only one that runs drift probes — because it changes *who the entity is*, not just what it can do. `evolve boot` changes instructions; `add skill` expands capabilities. Neither affects the behavioral baseline that drift probes measure.

For the normative specification of the Unified Evolution Protocol and the Capability Evolution Protocol, see `FCP-v1.0-RFC-Draft.md §12.2` and `HACA-Core-v1.0-RFC-Draft.md §5.1`.

---

## 13. Minimal Implementation: What You Actually Need to Build

To build a working FCP system from scratch, you need to implement:

### 13.1. The Directory Structure
Create the topology from Section 3. Start with just `persona/`, `state/`, `skills/`, and `memory/`. The rest can be added incrementally.

### 13.2. The Host Daemon (SIL)
A simple shell script or Python program that:
```
On boot trigger:
  1. Compute SHA-256 of persona/ files → compare to integrity.json
  2. Generate state/env.md
  3. Consolidate memory/inbox/*.msg → session.jsonl
  4. Assemble context: cat persona/* + state/env.md + skill manifests + active_context/* + tail of session.jsonl
  5. Call LLM API with assembled context → capture output
  6. Parse output for state delta (append to session.jsonl via spool) and skill requests
  7. For each skill request: validate → execute → append result to inbox
  8. Repeat from 3 until no pending skill requests
```

### 13.3. The Skill Cartridge (minimal example)
```
skills/
└── fs_read/
    ├── SKILL.md        ← "Read a file. Usage: {\"skill\":\"fs_read\",\"params\":{\"path\":\"...\"}}"
    └── manifest.json   ← {"name":"fs_read","capabilities":["read_file"],"security":{"sandbox":"workspaces_only"}}
```

The EL maps the `fs_read` skill to a script that reads only within `/workspaces/` and returns the content as a `SKILL_RESULT` envelope to `/memory/inbox/`.

### 13.4. A Minimal Bootstrap Probe Set
For an initial implementation, start with **5-10 probe pairs** derived from your entity's `persona/identity.md`. Questions about the entity's values, purpose, and constraints. Store them in `state/drift-probes.jsonl`. Run them at boot. If the answers drift significantly, pause operation.

As the system matures, expand to a minimum of **20 probes** with a pool of 60+ (see the FCP FAQ) for stronger statistical coverage and evasion resistance.

---

## 14. Filesystem Compatibility

| Filesystem | Status | Notes |
|---|---|---|
| ext4, XFS, Btrfs, ZFS, APFS | ✅ Fully supported | Atomic rename and O_APPEND are guaranteed |
| NTFS (via WSL2) | ⚠️ Conditional | Verify atomic rename semantics before deployment |
| NFS, CIFS/SMB, SSHFS | ❌ Not supported | Network filesystems do not reliably guarantee atomic rename |

The critical capabilities FCP requires from the filesystem:
- **`rename(2)` is atomic** within the filesystem
- **`O_APPEND` writes up to 4KB are atomic**
- **`fsync(2)` is supported** and reliable
- **`readdir(3)` returns consistent views** after a rename

---

## 15. Frequently Asked Questions

**Q: How do I integrate FCP with an existing LLM framework (LangChain, etc.)?**  
FCP is a directory structure + a set of conventions. The SIL that invokes your LLM can itself use LangChain, direct API calls, or a local model runner. FCP only cares about: (a) the context assembled for the LLM is from the MIL, and (b) the LLM's outputs go through the spooling mechanism before touching the MIL.

**Q: How expensive are the drift probes?**  
Each probe is one LLM API call (at `temperature=0`). With a recommended minimum of 20 probes, that's 20 API calls per boot. For most use cases, this is a small fraction of total usage. FCP also supports sampling a subset (e.g., 7 of 20 probes) for periodic mid-session checks.

**Q: Can the CPE modify its own `persona/` files?**  
Not directly. `persona/` files are cryptographically sealed and verified at every boot. Identity evolution is possible, but only via the Identity Update Protocol: an operator (or the `sys_endure` skill mediated through the EL) proposes changes, the SIL verifies the proposed new identity passes drift probing, and only then are the files updated and `integrity.json` re-anchored.

**Q: What happens if `integrity.json` itself is tampered with?**  
`integrity.json` is included in its own integrity record (its hash is stored separately, outside the FCP directory). In production, this external anchor is a hardware TPM, an operator-held hash, or a signed Git commit. Without an external anchor, `integrity.json` tampering is undetectable at the local level — this is acknowledged as a known limitation of HACA-Core, addressed by HACA-Full (out-of-band anchor) and HACA-Security (Byzantine host model).

**Q: How does the entity handle a very long session that exceeds the context window?**  
Phase 4 context loading respects the `context_budget` field in `env.md`. When the session tail would exceed the budget, older entries are dropped (the newest are always loaded first). The dropped entries remain in `session.jsonl` and can be paged back in via the active context mechanism if needed. The entity always has its full identity (`persona/`) and active memories (`active_context/*`) loaded — it only loses older session tail.

**Q: Is there a reference implementation I can copy from?**  
The authors have used boilerplate directory structures in their own prototypes. A minimal bootstrap directory is planned as a companion to this specification.

---

## 16. Status and Contributing

This Internet Draft is published for community review prior to formal IETF submission. The complete formal specification (with normative axioms, mathematical drift metrics, ACP schema normative language, and compliance test suites) is in the `fcp-spec/` directory.

**Feedback welcome via GitHub Issues:**
- Did you try to implement a minimal FCP? What was underdefined?
- Are the ACP envelope types clear enough to implement from this document?
- Is the boot phase sequence sufficient to understand the ordering requirements?
- Do you see portability issues on platforms not covered in Section 14?

---

## Normative References (Full Spec)

- [HACA-Arch](../../spec/HACA-Arch-1.0.0.md) — Root architecture overview (start here)
- [FCP Spec](FCP-1.0.0.md) — Complete FCP specification
- [HACA-Core](../../spec/HACA-Core-1.0.0.md) — Formal axioms and compliance tests
- [HACA-Arch](../../spec/HACA-Arch-1.0.0.md) — Abstract architecture and trust model
- *HACA-Security* (Planned) — Byzantine host model and cryptographic auditability